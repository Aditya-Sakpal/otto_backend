from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.repositories.company import CompanyRepository
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
from app.infrastructure.database.models.company import CompanyORM
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM
from app.core.logging import get_logger

logger = get_logger(__name__)


class CompanyService:
    """Service for managing company and company integration operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.company_repo = CompanyRepository(session)
        self.integration_repo = CompanyIntegrationRepository(session)

    async def create_company(
        self,
        name: str,
        reference_doc_url: str,
        sop_doc_url: str | None = None,
        csr_sop_doc_url: str | None = None,
        sales_sop_doc_url: str | None = None,
        phone_number: str | None = None,
        address: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CompanyORM:
        """
        Create a new company.

        Args:
            name: Company name
            reference_doc_url: URL to reference document in S3
            sop_doc_url: URL to SOP document in S3 (optional)
            csr_sop_doc_url: URL to CSR SOP document in S3 (optional)
            sales_sop_doc_url: URL to Sales SOP document in S3 (optional)
            phone_number: Company phone number (optional)
            address: Company address (optional)
            extra_metadata: Additional metadata (optional)

        Returns:
            Created CompanyORM instance
        """
        return await self.company_repo.create(
            name=name,
            phone_number=phone_number,
            address=address,
            reference_doc_url=reference_doc_url,
            sop_doc_url=sop_doc_url,
            csr_sop_doc_url=csr_sop_doc_url,
            sales_sop_doc_url=sales_sop_doc_url,
            extra_metadata=extra_metadata
        )

    async def create_company_integration(
        self,
        company_id: UUID,
        location_id: str | None = None,
        crm_provider: str | None = None,
        crm_api_key: str | None = None,
        crm_company_id: str | None = None,
        voip_provider: str | None = None,
        voip_api_key: str | None = None,
        voip_access_key: str | None = None,
        voip_company_id: str | None = None,
        extra_metadata: dict | None = None,
        st_tenant_id: str | None = None,
        st_client_id: str | None = None,
        st_client_secret: str | None = None,
    ) -> CompanyIntegrationORM | None:
        """
        Create a company integration record with encrypted API keys.
        Only creates if at least one integration (CRM or VOIP) is provided.

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
            Created CompanyIntegrationORM instance or None if no integrations provided
        """
        # Check if any integration data is provided
        has_crm = bool(crm_provider and crm_api_key)
        has_voip = bool(voip_provider and voip_api_key)
        has_st = bool(st_tenant_id and st_client_id and st_client_secret)

        if not has_crm and not has_voip and not has_st:
            logger.info(f"No integration data provided for company {company_id}, skipping integration creation")
            return None

        return await self.integration_repo.create(
            company_id=company_id,
            location_id=location_id,
            crm_provider=crm_provider,
            crm_api_key=crm_api_key,
            crm_company_id=crm_company_id,
            voip_provider=voip_provider,
            voip_api_key=voip_api_key,
            voip_access_key=voip_access_key,
            voip_company_id=voip_company_id,
            extra_metadata=extra_metadata,
            st_tenant_id=st_tenant_id,
            st_client_id=st_client_id,
            st_client_secret=st_client_secret,
        )

    async def get_company_by_id(self, company_id: UUID) -> CompanyORM | None:
        """
        Get a company by ID.

        Args:
            company_id: Company UUID

        Returns:
            CompanyORM instance or None if not found
        """
        return await self.company_repo.get_by_id(company_id)

    async def get_company_integration(self, company_id: UUID) -> CompanyIntegrationORM | None:
        """
        Get company integration by company ID.

        Args:
            company_id: Company UUID

        Returns:
            CompanyIntegrationORM instance or None if not found
        """
        return await self.integration_repo.get_by_company_id(company_id)

    async def update_company(
        self,
        company_id: UUID,
        name: str | None = None,
        phone_number: str | None = None,
        address: str | None = None,
        reference_doc_url: str | None = None,
        sop_doc_url: str | None = None,
        csr_sop_doc_url: str | None = None,
        sales_sop_doc_url: str | None = None,
        extra_metadata: dict | None = None,
        follow_up_manual_review_enabled: bool | None = None,
    ) -> CompanyORM | None:
        """
        Update a company.

        Args:
            company_id: Company UUID
            name: Company name (optional)
            phone_number: Company phone number (optional)
            address: Company address (optional)
            reference_doc_url: URL to reference document (optional)
            sop_doc_url: URL to SOP document (optional)
            csr_sop_doc_url: URL to CSR SOP document (optional)
            sales_sop_doc_url: URL to Sales SOP document (optional)
            extra_metadata: Additional metadata (optional)
            follow_up_manual_review_enabled: Contextual follow-up draft-before-send toggle (optional)

        Returns:
            Updated CompanyORM instance or None if not found
        """
        return await self.company_repo.update(
            company_id=company_id,
            name=name,
            phone_number=phone_number,
            address=address,
            reference_doc_url=reference_doc_url,
            sop_doc_url=sop_doc_url,
            csr_sop_doc_url=csr_sop_doc_url,
            sales_sop_doc_url=sales_sop_doc_url,
            extra_metadata=extra_metadata,
            follow_up_manual_review_enabled=follow_up_manual_review_enabled,
        )

    async def update_company_integration(
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
        st_tenant_id: str | None = None,
        st_client_id: str | None = None,
        st_client_secret: str | None = None,
    ) -> CompanyIntegrationORM | None:
        """
        Update a company integration.

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
            st_tenant_id: ServiceTitan tenant ID (optional)
            st_client_id: ServiceTitan client ID (optional)
            st_client_secret: ServiceTitan client secret - will be encrypted (optional)

        Returns:
            Updated CompanyIntegrationORM instance or None if not found
        """
        return await self.integration_repo.update(
            company_id=company_id,
            location_id=location_id,
            crm_provider=crm_provider,
            crm_api_key=crm_api_key,
            crm_company_id=crm_company_id,
            voip_provider=voip_provider,
            voip_api_key=voip_api_key,
            voip_company_id=voip_company_id,
            extra_metadata=extra_metadata,
            st_tenant_id=st_tenant_id,
            st_client_id=st_client_id,
            st_client_secret=st_client_secret,
        )

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
        return await self.integration_repo.upsert_company_integration(
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

    async def has_complete_onboarding(self, company_id: UUID) -> bool:
        """
        Check if a company has complete onboarding (company exists).
        Note: Integration is now optional, so we only check for company existence.

        Args:
            company_id: Company UUID

        Returns:
            True if company exists, False otherwise
        """
        company = await self.company_repo.get_by_id(company_id)
        return company is not None

    async def get_decrypted_api_keys(self, company_id: UUID) -> dict[str, str | None]:
        """
        Get decrypted API keys for a company.

        Args:
            company_id: Company UUID

        Returns:
            Dictionary with 'crm_api_key' and 'voip_api_key' (None if not set)
        """
        return {
            'crm_api_key': await self.integration_repo.get_decrypted_crm_key(company_id),
            'voip_api_key': await self.integration_repo.get_decrypted_voip_key(company_id)
        }

    async def get_company_id_by_location_id(self, location_id: str) -> UUID | None:
        """
        Get company_id from location_id.

        Args:
            location_id: GHL location ID

        Returns:
            Company UUID or None if not found
        """
        return await self.integration_repo.get_company_id_by_location_id(location_id)
