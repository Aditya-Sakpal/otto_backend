from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.logging import get_logger
from app.domain.models.company_integration import CompanyIntegration
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM
from app.core.encryption import encrypt_api_key, decrypt_api_key

logger = get_logger(__name__)


class CompanyIntegrationRepository:
    """Repository for CompanyIntegration database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        company_id: UUID,
        location_id: str | None = None,
        crm_provider: str | None = None,
        crm_api_key: str | None = None,
        crm_company_id: str | None = None,
        voip_provider: str | None = None,
        voip_api_key: str | None = None,
        voip_company_id: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CompanyIntegrationORM:
        """
        Create company integration with encrypted API keys.

        Args:
            company_id: ID of the company
            location_id: GHL location ID (optional)
            crm_provider: CRM provider name (optional)
            crm_api_key: CRM API key - will be encrypted (optional)
            crm_company_id: CRM company ID (optional)
            voip_provider: VoIP provider name (optional)
            voip_api_key: VoIP API key - will be encrypted (optional)
            voip_company_id: VoIP company ID (optional)
            extra_metadata: Additional metadata (optional)

        Returns:
            Created CompanyIntegrationORM instance
        """
        try:
            # Encrypt API keys if provided
            crm_encrypted_key = encrypt_api_key(crm_api_key) if crm_api_key else None
            voip_encrypted_key = encrypt_api_key(voip_api_key) if voip_api_key else None

            orm_obj = CompanyIntegrationORM(
                company_id=company_id,
                location_id=location_id or "",
                crm_api_encrypted_key=crm_encrypted_key or "",
                crm_provider=crm_provider or "",
                crm_company_id=crm_company_id,
                voip_api_encrypted_key=voip_encrypted_key or "",
                voip_provider=voip_provider or "",
                voip_company_id=voip_company_id,
                extra_metadata=extra_metadata or {}
            )
            self.session.add(orm_obj)
            await self.session.flush()
            await self.session.refresh(orm_obj)

            logger.info(f"Created company integration for company {company_id}")
            return orm_obj
        except Exception as e:
            logger.error(f"Error creating company integration: {e}")
            raise e

    async def update(
        self,
        company_id: UUID,
        location_id: str | None = None,
        crm_provider: str | None = None,
        crm_api_key: str | None = None,
        crm_company_id: str | None = None,
        voip_provider: str | None = None,
        voip_api_key: str | None = None,
        voip_company_id: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CompanyIntegrationORM | None:
        """
        Update company integration.
        Note: API keys will be re-encrypted if provided.

        Args:
            company_id: Company UUID
            location_id: GHL location ID (optional)
            crm_provider: CRM provider name (optional)
            crm_api_key: CRM API key - will be encrypted (optional)
            crm_company_id: CRM company ID (optional)
            voip_provider: VoIP provider name (optional)
            voip_api_key: VoIP API key - will be encrypted (optional)
            voip_company_id: VoIP company ID (optional)
            extra_metadata: Additional metadata (optional)

        Returns:
            Updated CompanyIntegrationORM instance or None if not found
        """
        try:
            orm_obj = await self.get_by_company_id(company_id)
            if not orm_obj:
                return None

            if location_id is not None:
                orm_obj.location_id = location_id
            if crm_provider is not None:
                orm_obj.crm_provider = crm_provider
            if crm_api_key is not None:
                orm_obj.crm_api_encrypted_key = encrypt_api_key(crm_api_key)
            if crm_company_id is not None:
                orm_obj.crm_company_id = crm_company_id
            if voip_provider is not None:
                orm_obj.voip_provider = voip_provider
            if voip_api_key is not None:
                orm_obj.voip_api_encrypted_key = encrypt_api_key(voip_api_key)
            if voip_company_id is not None:
                orm_obj.voip_company_id = voip_company_id
            if extra_metadata is not None:
                orm_obj.extra_metadata = extra_metadata

            await self.session.flush()
            await self.session.refresh(orm_obj)

            logger.info(f"Updated company integration for company {company_id}")
            return orm_obj
        except Exception as e:
            logger.error(f"Error updating company integration: {e}")
            raise e

    async def upsert_company_integration(
        self,
        company_id: UUID,
        location_id: str | None = None,
        crm_provider: str | None = None,
        crm_api_key: str | None = None,
        crm_company_id: str | None = None,
        voip_provider: str | None = None,
        voip_api_key: str | None = None,
        voip_company_id: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CompanyIntegrationORM:
        """
        Upsert company integration (create if not exists, update if exists).

        Args:
            company_id: Company UUID
            location_id: GHL location ID (optional)
            crm_provider: CRM provider name (optional)
            crm_api_key: CRM API key - will be encrypted (optional)
            crm_company_id: CRM company ID (optional)
            voip_provider: VoIP provider name (optional)
            voip_api_key: VoIP API key - will be encrypted (optional)
            voip_company_id: VoIP company ID (optional)
            extra_metadata: Additional metadata (optional)

        Returns:
            Created or updated CompanyIntegrationORM instance
        """
        try:
            existing = await self.get_by_company_id(company_id)

            if existing:
                return await self.update(
                    company_id=company_id,
                    location_id=location_id,
                    crm_provider=crm_provider,
                    crm_api_key=crm_api_key,
                    crm_company_id=crm_company_id,
                    voip_provider=voip_provider,
                    voip_api_key=voip_api_key,
                    voip_company_id=voip_company_id,
                    extra_metadata=extra_metadata
                )
            else:
                return await self.create(
                    company_id=company_id,
                    location_id=location_id,
                    crm_provider=crm_provider,
                    crm_api_key=crm_api_key,
                    crm_company_id=crm_company_id,
                    voip_provider=voip_provider,
                    voip_api_key=voip_api_key,
                    voip_company_id=voip_company_id,
                    extra_metadata=extra_metadata
                )
        except Exception as e:
            logger.error(f"Error upserting company integration: {e}")
            raise e

    async def get_by_company_id(self, company_id: UUID) -> CompanyIntegrationORM | None:
        """
        Get company integration by company_id.

        Args:
            company_id: Company UUID

        Returns:
            CompanyIntegrationORM instance or None if not found
        """
        try:
            result = await self.session.execute(
                select(CompanyIntegrationORM).where(
                    CompanyIntegrationORM.company_id == company_id
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting company integration by company_id: {e}")
            raise e

    async def get_by_id(self, integration_id: UUID) -> CompanyIntegrationORM | None:
        """
        Get company integration by integration ID.

        Args:
            integration_id: Integration UUID

        Returns:
            CompanyIntegrationORM instance or None if not found
        """
        try:
            return await self.session.get(CompanyIntegrationORM, integration_id)
        except Exception as e:
            logger.error(f"Error getting company integration by id: {e}")
            raise e

    async def get_company_id_by_location_id(self, location_id: str) -> UUID | None:
        """
        Get company_id from location_id.

        Args:
            location_id: GHL location ID

        Returns:
            Company UUID or None if not found
        """
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

    async def get_company_id_by_voip_company_id(self, voip_company_id: str) -> UUID | None:
        """
        Get company_id from voip_company_id.

        Args:
            voip_company_id: VoIP company ID

        Returns:
            Company UUID or None if not found
        """
        try:
            result = await self.session.execute(
                select(CompanyIntegrationORM).where(
                    CompanyIntegrationORM.voip_company_id == voip_company_id
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return orm_obj.company_id
            return None
        except Exception as e:
            logger.error(f"Error getting company_id by voip_company_id: {e}")
            raise e

    async def get_voip_api_encrypted_key_by_voip_company_id(self, company_id: str) -> str | None:
        """
        Get voip_api_encrypted_key from company_id.

        Args:
            company_id: voip_company_id

        Returns:
            Encrypted VoIP API key or None if not found
        """
        try:
            result = await self.session.execute(
                select(CompanyIntegrationORM).where(
                    CompanyIntegrationORM.voip_company_id == company_id
                )
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return orm_obj.voip_api_encrypted_key
            return None
        except Exception as e:
            logger.error(f"Error getting voip_api_encrypted_key by company_id: {e}")
            raise e

    async def get_decrypted_crm_key(self, company_id: UUID) -> str | None:
        """
        Get decrypted CRM API key for a company.

        Args:
            company_id: Company UUID

        Returns:
            Decrypted CRM API key or None if not found/not set
        """
        try:
            integration = await self.get_by_company_id(company_id)
            if not integration or not integration.crm_api_encrypted_key:
                return None

            return decrypt_api_key(integration.crm_api_encrypted_key)
        except Exception as e:
            logger.error(f"Error getting decrypted CRM key: {e}")
            raise e

    async def get_decrypted_voip_key(self, company_id: UUID) -> str | None:
        """
        Get decrypted VoIP API key for a company.

        Args:
            company_id: Company UUID

        Returns:
            Decrypted VoIP API key or None if not found/not set
        """
        try:
            integration = await self.get_by_company_id(company_id)
            if not integration or not integration.voip_api_encrypted_key:
                return None

            return decrypt_api_key(integration.voip_api_encrypted_key)
        except Exception as e:
            logger.error(f"Error getting decrypted VoIP key: {e}")
            raise e

    async def delete(self, company_id: UUID) -> bool:
        """
        Delete company integration by company_id.

        Args:
            company_id: Company UUID

        Returns:
            True if deleted, False if not found
        """
        try:
            integration = await self.get_by_company_id(company_id)
            if not integration:
                return False

            await self.session.delete(integration)
            await self.session.flush()

            logger.info(f"Deleted company integration for company {company_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting company integration: {e}")
            raise e

    async def _to_domain(self, orm_obj: CompanyIntegrationORM) -> CompanyIntegration:
        """
        Convert ORM model to domain model.

        Args:
            orm_obj: CompanyIntegrationORM instance

        Returns:
            CompanyIntegration domain model
        """
        return CompanyIntegration(
            id=orm_obj.id,
            company_id=orm_obj.company_id,
            location_id=orm_obj.location_id,
            crm_provider=orm_obj.crm_provider,
            crm_company_id=orm_obj.crm_company_id,
            voip_provider=orm_obj.voip_provider,
            voip_company_id=orm_obj.voip_company_id,
            extra_metadata=orm_obj.extra_metadata
        )
