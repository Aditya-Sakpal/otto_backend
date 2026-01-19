from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.company_integration import CompanyIntegration
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM

logger = get_logger(__name__)

class CompanyIntegrationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert_company_integration(self, company_id: str, location_id: str, encrypted_key: str, provider: str):
        """Upsert company integration."""
        try:
            existing = await self.session.execute(
                select(CompanyIntegrationORM).where(CompanyIntegrationORM.company_id == company_id)
            )
            orm_obj = existing.scalar_one_or_none()
            if orm_obj:
                return await self.update(orm_obj.id, company_id, location_id, encrypted_key, provider)
            else:
                return await self.create(company_id, location_id, encrypted_key, provider)
        except Exception as e:
            logger.error(f"Error upserting company integration: {e}")
            raise e

    async def update(self, company_id: str, location_id: str, encrypted_key: str, provider: str):
        """Update company integration."""
        try:
            orm_obj = await self.session.get(CompanyIntegrationORM, company_id)
            if not orm_obj:
                return None
            orm_obj.location_id = location_id
            orm_obj.encrypted_key = encrypted_key
            orm_obj.provider = provider
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return orm_obj
        except Exception as e:
            logger.error(f"Error updating company integration: {e}")
            raise e

    async def create(self, company_id: str, location_id: str, encrypted_key: str, provider: str):
        """Create company integration."""
        try:
            orm_obj = CompanyIntegrationORM(
                company_id=company_id,
                location_id=location_id,
                encrypted_key=encrypted_key,
                provider=provider
            )
            self.session.add(orm_obj)
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return orm_obj
        except Exception as e:
            logger.error(f"Error creating company integration: {e}")
            raise e

    async def get_company_id_by_location_id(self, location_id: str):
        """Get company_id from location_id."""
        try:
            result = await self.session.execute(
                select(CompanyIntegrationORM).where(
                    CompanyIntegrationORM.location_id == location_id
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return orm_obj.company_id
            return None
        except Exception as e:
            logger.error(f"Error getting company_id by location_id: {e}")
            raise e

    async def get_voip_api_encrypted_key_by_company_id(self, company_id):
        """Get voip_api_encrypted_key from company_id."""
        try:
            result = await self.session.execute(
                select(CompanyIntegrationORM).where(
                    CompanyIntegrationORM.company_id == company_id
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return orm_obj.voip_api_encrypted_key
            return None
        except Exception as e:
            logger.error(f"Error getting voip_api_encrypted_key by company_id: {e}")
            raise e

    async def _to_domain(self, orm_obj: CompanyIntegrationORM) -> CompanyIntegration:
        """Convert ORM model to domain model."""
        return CompanyIntegration(
            id=orm_obj.id,
            company_id=orm_obj.company_id,
            location_id=orm_obj.location_id,
            encrypted_key=orm_obj.encrypted_key,
            provider=orm_obj.provider
        )
