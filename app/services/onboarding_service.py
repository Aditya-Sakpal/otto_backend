"""
Onboarding Service.

Orchestrates the full onboarding flow: idempotency check, S3 uploads,
company/user creation, tenant config setup, and JWT token generation.
"""
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import get_password_hash, create_access_token, create_refresh_token
from app.domain.enums import UserRole
from app.domain.users.models import User
from app.domain.users.repository import UserRepository
from app.infrastructure.database.models.user import UserORM
from app.services.company_service import CompanyService
from app.services.tenant_config_service import TenantConfigService

logger = get_logger(__name__)


@dataclass
class OnboardingResult:
    """Internal result from the onboarding flow."""
    user: User
    access_token: str
    refresh_token: str
    is_existing: bool
    csr_sop_doc_url: str | None = None
    sales_sop_doc_url: str | None = None
    company_id: UUID | None = None


class OnboardingService:
    """Service for orchestrating the complete onboarding flow."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.company_service = CompanyService(session)
        self.tenant_config_service = TenantConfigService(session)

    async def complete_onboarding(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        company_name: str,
        s3_service,
        reference_doc: UploadFile | None,
        csr_sop_doc: UploadFile | None,
        sales_sop_doc: UploadFile | None,
        phone_number: str | None,
        address: str | None,
        location_id: str | None,
        crm_provider: str | None,
        crm_api_key: str | None,
        crm_company_id: str | None,
        voip_provider: str | None,
        voip_api_key: str | None,
        voip_access_key: str | None,
        voip_company_id: str | None,
        st_tenant_id: str | None,
        st_client_id: str | None,
        st_client_secret: str | None,
        ghost_mode_enabled: bool,
    ) -> OnboardingResult:
        """Run the full onboarding flow. Returns OnboardingResult."""

        # 1. Idempotency check
        existing = await self._check_existing_user(email)
        if existing:
            return existing

        def _has_upload_file(f: UploadFile | None) -> bool:
            return f is not None and bool((f.filename or "").strip())

        needs_s3_upload = (
            _has_upload_file(reference_doc)
            or _has_upload_file(csr_sop_doc)
            or _has_upload_file(sales_sop_doc)
        )

        # 2. Upload documents to S3 (only when at least one file is provided)
        uploaded_keys: list[tuple[str, str]] = []
        try:
            if needs_s3_upload:
                if not s3_service:
                    raise ValueError("S3 service is not configured but file uploads were requested")
                ref_url, csr_url, sales_url, uploaded_keys = await self._upload_documents(
                    s3_service, email, reference_doc, csr_sop_doc, sales_sop_doc,
                )
            else:
                ref_url = csr_url = sales_url = None

            # 3. Race-condition re-check
            existing_recheck = await self._check_existing_user(email)
            if existing_recheck:
                if uploaded_keys and s3_service:
                    await self._cleanup_s3_files(s3_service, uploaded_keys)
                return existing_recheck

            # 4. Create company + integration + user (atomic)
            user, company_id = await self._create_company_and_user(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                company_name=company_name,
                ref_url=ref_url,
                csr_url=csr_url,
                sales_url=sales_url,
                phone_number=phone_number,
                address=address,
                location_id=location_id,
                crm_provider=crm_provider,
                crm_api_key=crm_api_key,
                crm_company_id=crm_company_id,
                voip_provider=voip_provider,
                voip_api_key=voip_api_key,
                voip_access_key=voip_access_key,
                voip_company_id=voip_company_id,
                st_tenant_id=st_tenant_id,
                st_client_id=st_client_id,
                st_client_secret=st_client_secret,
                ghost_mode_enabled=ghost_mode_enabled,
            )

            # 5. Tenant config (best-effort, post-commit)
            await self._create_default_tenant_config(
                company_id=company_id,
                company_name=company_name,
            )

            # 6. Generate JWT tokens
            access_token, refresh_token = self._generate_tokens(user)

            return OnboardingResult(
                user=user,
                access_token=access_token,
                refresh_token=refresh_token,
                is_existing=False,
                csr_sop_doc_url=csr_url,
                sales_sop_doc_url=sales_url,
                company_id=company_id,
            )
        except Exception:
            if uploaded_keys and s3_service:
                await self._cleanup_s3_files(s3_service, uploaded_keys)
            raise

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _check_existing_user(self, email: str) -> OnboardingResult | None:
        """Return OnboardingResult if user already onboarded, else None."""
        existing_user = await self.user_repo.get_by_email(email)
        if not existing_user:
            return None

        if existing_user.company_id:
            existing_company = await self.company_service.get_company_by_id(existing_user.company_id)
            if existing_company:
                logger.info(f"Onboarding already complete for {email}, returning existing user")
                user = self.user_repo._to_domain(existing_user)
                access_token, refresh_token = self._generate_tokens(user)
                return OnboardingResult(
                    user=user,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    is_existing=True,
                    company_id=existing_user.company_id,
                )

        raise ValueError(
            f"User with email {email} already exists but onboarding is incomplete. "
            "Please contact support."
        )

    async def _upload_documents(
        self,
        s3_service,
        email: str,
        reference_doc: UploadFile | None,
        csr_sop_doc: UploadFile | None,
        sales_sop_doc: UploadFile | None,
    ) -> tuple[str | None, str | None, str | None, list[tuple[str, str]]]:
        """Upload docs to S3. Returns (ref_url, csr_url, sales_url, uploaded_keys)."""
        uploaded_keys: list[tuple[str, str]] = []

        ref_url: str | None = None
        if reference_doc and (reference_doc.filename or "").strip():
            reference_doc_bytes = await reference_doc.read()
            reference_s3_key = s3_service.generate_s3_key(
                prefix="user-onboarding-docs",
                filename=f"{email}_{reference_doc.filename}",
                extension=reference_doc.filename.split(".")[-1] if "." in reference_doc.filename else "pdf",
            )
            ref_url = await s3_service.upload_file(
                file_bytes=reference_doc_bytes,
                s3_key=reference_s3_key,
                content_type=reference_doc.content_type,
                bucket_type="documents",
            )
            uploaded_keys.append((reference_s3_key, "documents"))

        csr_url = None
        if csr_sop_doc and csr_sop_doc.filename:
            csr_bytes = await csr_sop_doc.read()
            csr_s3_key = s3_service.generate_s3_key(
                prefix="user-onboarding-docs",
                filename=f"{email}_csr_{csr_sop_doc.filename}",
                extension=csr_sop_doc.filename.split(".")[-1] if "." in csr_sop_doc.filename else "pdf",
            )
            csr_url = await s3_service.upload_file(
                file_bytes=csr_bytes,
                s3_key=csr_s3_key,
                content_type=csr_sop_doc.content_type,
                bucket_type="documents",
            )
            uploaded_keys.append((csr_s3_key, "documents"))

        sales_url = None
        if sales_sop_doc and sales_sop_doc.filename:
            sales_bytes = await sales_sop_doc.read()
            sales_s3_key = s3_service.generate_s3_key(
                prefix="user-onboarding-docs",
                filename=f"{email}_sales_{sales_sop_doc.filename}",
                extension=sales_sop_doc.filename.split(".")[-1] if "." in sales_sop_doc.filename else "pdf",
            )
            sales_url = await s3_service.upload_file(
                file_bytes=sales_bytes,
                s3_key=sales_s3_key,
                content_type=sales_sop_doc.content_type,
                bucket_type="documents",
            )
            uploaded_keys.append((sales_s3_key, "documents"))

        logger.info(f"Uploaded documents to S3 for {email}")
        return ref_url, csr_url, sales_url, uploaded_keys

    async def _create_company_and_user(
        self,
        *,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        company_name: str,
        ref_url: str | None,
        csr_url: str | None,
        sales_url: str | None,
        phone_number: str | None,
        address: str | None,
        location_id: str | None,
        crm_provider: str | None,
        crm_api_key: str | None,
        crm_company_id: str | None,
        voip_provider: str | None,
        voip_api_key: str | None,
        voip_access_key: str | None,
        voip_company_id: str | None,
        st_tenant_id: str | None,
        st_client_id: str | None,
        st_client_secret: str | None,
        ghost_mode_enabled: bool,
    ) -> tuple[User, UUID]:
        """Create company, integration, and user atomically. Returns (User, company_id)."""
        try:
            extra_metadata = {}
            if crm_company_id:
                extra_metadata["crm_company_id"] = crm_company_id
            if ghost_mode_enabled:
                extra_metadata["ghost_mode_enabled"] = True

            company_orm = await self.company_service.create_company(
                name=company_name,
                phone_number=phone_number,
                address=address,
                reference_doc_url=ref_url,
                csr_sop_doc_url=csr_url,
                sales_sop_doc_url=sales_url,
                extra_metadata=extra_metadata if extra_metadata else None,
            )
            company_id = company_orm.id

            await self.company_service.create_company_integration(
                company_id=company_id,
                location_id=location_id,
                crm_provider=crm_provider,
                crm_api_key=crm_api_key,
                crm_company_id=crm_company_id,
                voip_provider=voip_provider,
                voip_api_key=voip_api_key,
                voip_access_key=voip_access_key,
                voip_company_id=voip_company_id,
                st_tenant_id=st_tenant_id,
                st_client_id=st_client_id,
                st_client_secret=st_client_secret,
            )

            user_orm = UserORM(
                email=email,
                password_hash=get_password_hash(password),
                role=UserRole.EXECUTIVE.value,
                first_name=first_name,
                last_name=last_name,
                company_id=company_id,
                is_active=True,
            )
            self.session.add(user_orm)
            await self.session.flush()
            await self.session.refresh(user_orm)

            await self.session.commit()

            user = self.user_repo._to_domain(user_orm)
            logger.info(f"Created user {email} with company {company_name}")
            return user, company_id

        except Exception:
            await self.session.rollback()
            raise

    async def _create_default_tenant_config(
        self,
        company_id: UUID,
        company_name: str,
    ) -> None:
        """Best-effort: create tenant config for the new company."""
        try:
            await self.tenant_config_service.create_config(
                company_id=company_id,
                company_name=company_name,
            )
            logger.info(f"Created default tenant config for company {company_id}")
        except Exception as e:
            logger.error(
                f"Failed to create default tenant config for company {company_id}: {e}",
                exc_info=True,
            )

    def _generate_tokens(self, user: User) -> tuple[str, str]:
        """Generate access + refresh JWT tokens for a user."""
        full_name = " ".join(p for p in [user.first_name, user.last_name] if p) or None
        access_token = create_access_token(
            user_id=user.id,
            role=user.role,
            company_id=user.company_id,
            name=full_name,
        )
        refresh_token = create_refresh_token(user_id=user.id)
        return access_token, refresh_token

    @staticmethod
    async def _cleanup_s3_files(s3_service, uploaded_keys: list[tuple[str, str]]) -> None:
        """Clean up uploaded S3 files on failure."""
        for s3_key, bucket_type in uploaded_keys:
            try:
                await s3_service.delete_file(s3_key, bucket_type)
                logger.info(f"Cleaned up S3 file: {s3_key}")
            except Exception as e:
                logger.warning(f"Failed to cleanup S3 file {s3_key}: {e}")
