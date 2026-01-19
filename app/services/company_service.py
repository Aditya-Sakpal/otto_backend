from app.core.config import settings
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
from app.services import ghl_service
from app.services.ghl_service import GHLService

from sqlalchemy.ext.asyncio import AsyncSession

class CompanyService:
    def __init__(self, session: AsyncSession):
        self.company_integration_repo = CompanyIntegrationRepository(session)
        self.ghl_service = GHLService(bearer_token=settings.GHL_BEARER_TOKEN)

    async def add_crm_integration(self, company_id: str, api_key: str):
        # 1. Verification Logic
        location_id = await self.ghl_service.verify_and_get_location_id_async(api_key)
        if not location_id:
            raise ValueError("Invalid GHL API Key")

        # 2. Business Logic (Encryption)
        encrypted_key = self.encrypt_key(api_key)

        # 3. Repository Persistence
        return self.repo.upsert_company_integration(
            company_id=company_id,
            location_id=location_id,
            encrypted_key=encrypted_key,
            provider="gohighlevel"
        )

    def encrypt_key(self, key: str) -> str:
        return self.ghl_service.encrypt_key(key)
