"""
Proxy number pool management service.

Manages the lifecycle of Twilio proxy phone numbers:
- Provisioning new numbers from Twilio
- Allocating numbers to proxy sessions
- Deallocating and applying cooldown
- Pool health monitoring
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.proxy_number import ProxyNumber
from app.infrastructure.integrations.twilio_client import get_twilio_client
from app.infrastructure.repositories.proxy_number import ProxyNumberRepository

logger = get_logger(__name__)

# Minimum available numbers before warning
LOW_POOL_THRESHOLD = 3


class NoAvailableProxyNumberError(Exception):
    """No proxy numbers available for a company."""

    def __init__(self, company_id: UUID):
        self.company_id = company_id
        super().__init__(
            f"No available proxy numbers for company {company_id}. "
            "Pool may be exhausted or all numbers are in cooldown."
        )


class ProxyPoolService:
    """Manages the pool of proxy phone numbers per company."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ProxyNumberRepository(session)
        self.twilio = get_twilio_client()

    async def provision_number(
        self, company_id: UUID, area_code: Optional[str] = None
    ) -> ProxyNumber:
        """
        Purchase a new Twilio number and add it to the company's pool.

        The number is configured with voice_url and sms_url pointing
        to our webhook endpoints.
        """
        if not self.twilio.is_available():
            raise RuntimeError("Twilio client not configured")

        result = self.twilio.provision_number(area_code=area_code)

        proxy = ProxyNumber(
            company_id=company_id,
            phone_number=result["phone_number"],
            twilio_sid=result["sid"],
            friendly_name=result["friendly_name"],
            region=area_code,
        )
        created = await self.repo.create(proxy)
        logger.info(
            "Provisioned proxy number",
            company_id=str(company_id),
            phone_number=result["phone_number"],
        )
        return created

    async def allocate_number(self, company_id: UUID) -> ProxyNumber:
        """
        Get an available number from the pool and mark as assigned.

        Uses FOR UPDATE SKIP LOCKED for safe concurrent allocation.
        Raises NoAvailableProxyNumberError if pool is empty.
        """
        proxy = await self.repo.get_available_for_company(company_id)
        if not proxy:
            raise NoAvailableProxyNumberError(company_id)

        await self.repo.mark_assigned(proxy.id)
        logger.info(
            "Allocated proxy number",
            proxy_number_id=str(proxy.id),
            company_id=str(company_id),
        )
        return proxy

    async def deallocate_number(self, proxy_number_id: UUID) -> None:
        """
        Return a number to the pool.

        Sets is_assigned=False and last_released_at=now().
        The 30-day cooldown is enforced by the allocation query filter.
        """
        await self.repo.mark_unassigned(proxy_number_id)
        logger.info("Deallocated proxy number", proxy_number_id=str(proxy_number_id))

    async def release_number(self, proxy_number_id: UUID) -> bool:
        """Release a number back to Twilio entirely (remove from pool)."""
        proxy = await self.repo.get_by_id(proxy_number_id)
        if not proxy:
            return False

        if self.twilio.is_available():
            self.twilio.release_number(proxy.twilio_sid)

        await self.repo.delete(proxy_number_id)
        logger.info(
            "Released proxy number to Twilio",
            proxy_number_id=str(proxy_number_id),
        )
        return True

    async def get_pool_status(self, company_id: UUID) -> dict:
        """
        Get pool statistics for a company.

        Returns: total, assigned, available, cooling_down counts
        and a low_pool warning flag.
        """
        stats = await self.repo.count_by_company(company_id)
        stats["low_pool_warning"] = stats["available"] < LOW_POOL_THRESHOLD
        return stats
