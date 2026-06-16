"""
Tests for ProxyPoolService — number allocation, deallocation, provisioning, pool status.

Uses pytest-asyncio with mocked database session and Twilio client.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.proxy_pool_service import (
    ProxyPoolService,
    NoAvailableProxyNumberError,
    LOW_POOL_THRESHOLD,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_twilio():
    twilio = MagicMock()
    twilio.is_available.return_value = True
    twilio.provision_number.return_value = {
        "phone_number": "+15551230000",
        "sid": "PN_test_sid",
        "friendly_name": "(555) 123-0000",
    }
    return twilio


@pytest.fixture
def service(mock_db, mock_twilio):
    with patch("app.services.proxy_pool_service.get_twilio_client", return_value=mock_twilio):
        svc = ProxyPoolService(mock_db)
        svc.repo = AsyncMock()
        return svc


# ── allocate_number ──────────────────────────────────────────────────────────


class TestAllocateNumber:
    @pytest.mark.asyncio
    async def test_success(self, service):
        company_id = uuid4()
        mock_proxy = MagicMock()
        mock_proxy.id = uuid4()
        mock_proxy.phone_number = "+15551230000"
        service.repo.get_available_for_company = AsyncMock(return_value=mock_proxy)
        service.repo.mark_assigned = AsyncMock()

        result = await service.allocate_number(company_id)

        assert result == mock_proxy
        service.repo.get_available_for_company.assert_awaited_once_with(company_id)
        service.repo.mark_assigned.assert_awaited_once_with(mock_proxy.id)

    @pytest.mark.asyncio
    async def test_pool_exhausted(self, service):
        company_id = uuid4()
        service.repo.get_available_for_company = AsyncMock(return_value=None)

        with pytest.raises(NoAvailableProxyNumberError) as exc:
            await service.allocate_number(company_id)

        assert exc.value.company_id == company_id

    @pytest.mark.asyncio
    async def test_pool_exhausted_message(self, service):
        company_id = uuid4()
        service.repo.get_available_for_company = AsyncMock(return_value=None)

        with pytest.raises(NoAvailableProxyNumberError, match="No available proxy numbers"):
            await service.allocate_number(company_id)


# ── deallocate_number ────────────────────────────────────────────────────────


class TestDeallocateNumber:
    @pytest.mark.asyncio
    async def test_success(self, service):
        proxy_id = uuid4()
        service.repo.mark_unassigned = AsyncMock()

        await service.deallocate_number(proxy_id)

        service.repo.mark_unassigned.assert_awaited_once_with(proxy_id)


# ── provision_number ─────────────────────────────────────────────────────────


class TestProvisionNumber:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_twilio):
        company_id = uuid4()
        mock_created = MagicMock()
        service.repo.create = AsyncMock(return_value=mock_created)

        result = await service.provision_number(company_id, area_code="555")

        assert result == mock_created
        mock_twilio.provision_number.assert_called_once_with(area_code="555")
        service.repo.create.assert_awaited_once()

        # Verify the domain model passed to create has correct fields
        created_proxy = service.repo.create.call_args[0][0]
        assert created_proxy.company_id == company_id
        assert created_proxy.phone_number == "+15551230000"
        assert created_proxy.twilio_sid == "PN_test_sid"

    @pytest.mark.asyncio
    async def test_twilio_unavailable(self, service, mock_twilio):
        mock_twilio.is_available.return_value = False
        company_id = uuid4()

        with pytest.raises(RuntimeError, match="Twilio client not configured"):
            await service.provision_number(company_id)


# ── release_number ───────────────────────────────────────────────────────────


class TestReleaseNumber:
    @pytest.mark.asyncio
    async def test_success(self, service, mock_twilio):
        proxy_id = uuid4()
        mock_proxy = MagicMock()
        mock_proxy.twilio_sid = "PN_test_sid"
        service.repo.get_by_id = AsyncMock(return_value=mock_proxy)
        service.repo.delete = AsyncMock()

        result = await service.release_number(proxy_id)

        assert result is True
        mock_twilio.release_number.assert_called_once_with("PN_test_sid")
        service.repo.delete.assert_awaited_once_with(proxy_id)

    @pytest.mark.asyncio
    async def test_not_found(self, service):
        service.repo.get_by_id = AsyncMock(return_value=None)

        result = await service.release_number(uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_twilio_unavailable_still_deletes(self, service, mock_twilio):
        """Even if Twilio is offline, still remove from our pool."""
        mock_twilio.is_available.return_value = False
        proxy_id = uuid4()
        mock_proxy = MagicMock()
        mock_proxy.twilio_sid = "PN_test_sid"
        service.repo.get_by_id = AsyncMock(return_value=mock_proxy)
        service.repo.delete = AsyncMock()

        result = await service.release_number(proxy_id)

        assert result is True
        mock_twilio.release_number.assert_not_called()
        service.repo.delete.assert_awaited_once()


# ── get_pool_status ──────────────────────────────────────────────────────────


class TestGetPoolStatus:
    @pytest.mark.asyncio
    async def test_healthy_pool(self, service):
        company_id = uuid4()
        service.repo.count_by_company = AsyncMock(
            return_value={"total": 10, "assigned": 3, "available": 7, "cooling_down": 0}
        )

        result = await service.get_pool_status(company_id)

        assert result["total"] == 10
        assert result["available"] == 7
        assert result["low_pool_warning"] is False

    @pytest.mark.asyncio
    async def test_low_pool_warning(self, service):
        company_id = uuid4()
        service.repo.count_by_company = AsyncMock(
            return_value={"total": 5, "assigned": 4, "available": 1, "cooling_down": 0}
        )

        result = await service.get_pool_status(company_id)

        assert result["low_pool_warning"] is True

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, service):
        company_id = uuid4()
        service.repo.count_by_company = AsyncMock(
            return_value={
                "total": 10,
                "assigned": 10 - LOW_POOL_THRESHOLD,
                "available": LOW_POOL_THRESHOLD,
                "cooling_down": 0,
            }
        )

        result = await service.get_pool_status(company_id)

        # At threshold (not below) — no warning
        assert result["low_pool_warning"] is False

    @pytest.mark.asyncio
    async def test_empty_pool(self, service):
        company_id = uuid4()
        service.repo.count_by_company = AsyncMock(
            return_value={"total": 0, "assigned": 0, "available": 0, "cooling_down": 0}
        )

        result = await service.get_pool_status(company_id)

        assert result["low_pool_warning"] is True
        assert result["total"] == 0
