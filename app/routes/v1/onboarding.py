"""
Onboarding API routes.

Handles user/company creation, GHL integration, and document storage.
"""
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from pydantic import EmailStr

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
from app.core.security import get_password_hash
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.domain.schemas.onboarding import (
    OnboardingCompleteResponse,
    ValidateGHLRequest,
    ValidateGHLResponse,
    ValidateCTMRequest,
    ValidateCTMResponse,
    ValidateServiceTitanRequest,
    ValidateServiceTitanResponse,
)
from app.services.company_service import CompanyService
from app.services.ghl_service import GHLService
from app.services.ctm_service import CTMService
from app.infrastructure.integrations.servicetitan import ServiceTitanClient
from app.domain.users.repository import UserRepository
from app.infrastructure.database.models.user import UserORM
from app.domain.enums import UserRole

logger = get_logger(__name__)

router = APIRouter()

RESPONSES = {
    401: {"description": "Invalid credentials"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


@router.post("/validate-ghl", response_model=ValidateGHLResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_ghl(
    body: ValidateGHLRequest,
) -> ValidateGHLResponse:
    """
    Verify GoHighLevel credentials before final submission.

    Args:
        body: Validation request with location_id and api_key

    Returns:
        GHL company information if valid

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    try:
        result = await GHLService.verify_api_key(body.api_key, body.location_id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GHL API key or location ID"
            )

        return ValidateGHLResponse(
            company_id=result["company_id"],
            company_name=result["company_name"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating GHL credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error validating GHL credentials: {str(e)}"
        )


@router.post("/validate-ctm", response_model=ValidateCTMResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_ctm(
    body: ValidateCTMRequest,
) -> ValidateCTMResponse:
    """
    Verify Call Tracking Metrics (CTM) credentials before final submission.

    Args:
        body: Validation request with access_key and secret_key

    Returns:
        CTM company information if valid (secret_key, company_name, company_id)

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    try:
        result = await CTMService.verify_api_key(body.access_key, body.secret_key)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid CTM access key or secret key"
            )

        return ValidateCTMResponse(
            secret_key=result["secret_key"],
            company_name=result["company_name"],
            company_id=result["company_id"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating CTM credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error validating CTM credentials: {str(e)}"
        )

@router.post("/validate-servicetitan", response_model=ValidateServiceTitanResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_servicetitan(
    body: ValidateServiceTitanRequest,
) -> ValidateServiceTitanResponse:
    """
    Verify ServiceTitan credentials before final submission.

    Args:
        body: Validation request with tenant_id, client_id, client_secret, env

    Returns:
        Tenant info if valid

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    try:
        client = ServiceTitanClient(
            tenant_id=body.tenant_id,
            client_id=body.client_id,
            client_secret=body.client_secret,
        )
        result = await client.verify_credentials()
        return ValidateServiceTitanResponse(
            tenant_id=result["tenant_id"],
            status=result["status"],
        )
    except Exception as e:
        logger.error(f"Error validating ServiceTitan credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid ServiceTitan credentials: {str(e)}",
        )


@router.post("/complete", response_model=OnboardingCompleteResponse, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def complete_onboarding(
    background_tasks: BackgroundTasks,
    db: DbSession,
    firstName: str = Form(...),
    lastName: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    companyName: str = Form(...),
    reference_doc: UploadFile = File(...),
    # Optional SOP_documents (Handled to have atleast one from the frontend)
    csr_sop_doc: UploadFile | None = File(None),
    sales_sop_doc: UploadFile | None = File(None),
    # Optional company fields
    phone_number: str | None = Form(None),
    address: str | None = Form(None),
    # Optional integration fields
    location_id: str | None = Form(None),
    crm_provider: str | None = Form(None),
    crm_api_key: str | None = Form(None),
    crm_company_id: str | None = Form(None),
    voip_provider: str | None = Form(None),
    voip_api_key: str | None = Form(None),
    voip_company_id: str | None = Form(None),
    # Optional ServiceTitan integration fields
    st_tenant_id: str | None = Form(None),
    st_client_id: str | None = Form(None),
    st_client_secret: str | None = Form(None),
    # Ghost mode setting
    ghost_mode_enabled: bool = Form(False),
) -> OnboardingCompleteResponse:
    """
    Complete onboarding: create user, company, integration, and upload documents.

    This endpoint performs an idempotent, atomic operation:
    1. Validates all fields and files
    2. Checks for existing user/company (idempotency)
    3. Uploads documents to S3
    4. Creates Company, User, and CompanyIntegration records in a single transaction

    The operation is idempotent: if a user with the same email already exists,
    it returns the existing user data without creating duplicates.

    Required Args:
        firstName: User's first name
        lastName: User's last name
        email: User's email address
        password: User's password
        companyName: Company name
        reference_doc: Reference document file

    Optional Args:
        csr_sop_doc: CSR SOP document file (optional)
        sales_sop_doc: Sales SOP document file (optional)
        phone_number: Company phone number
        address: Company address
        location_id: GHL location ID
        crm_provider: CRM provider name
        crm_api_key: CRM API key (will be encrypted)
        crm_company_id: CRM company ID
        voip_provider: VoIP provider name
        voip_api_key: VoIP API key (will be encrypted)
        voip_company_id: VoIP company ID
        ghost_mode_enabled: Enable ghost mode availability for sales reps (default: False)
        db: Database session

    Returns:
        Created or existing user information (excluding password)

    Raises:
        HTTPException: 400 if validation fails, 500 if creation fails
    """
    # Validate that required files are present
    if not reference_doc.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reference_doc file is required"
        )

    # Get S3 service
    s3_service = get_s3_service()
    if not s3_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3 service is not configured"
        )

    # Initialize repositories and services
    user_repo = UserRepository(db)
    company_service = CompanyService(db)

    # Track uploaded S3 keys for cleanup on failure
    uploaded_s3_keys = []

    # Step 1: Check for existing user (idempotency check BEFORE S3 upload)
    existing_user = await user_repo.get_by_email(email)

    if existing_user:
        # User exists - check if it's a complete onboarding (has company)
        if existing_user.company_id:
            existing_company = await company_service.get_company_by_id(existing_user.company_id)

            if existing_company:
                # Check for integration (optional now, so complete onboarding just needs company)
                existing_integration = await company_service.get_company_integration(existing_user.company_id)

                # Complete onboarding exists - return existing data (idempotent)
                logger.info(f"Onboarding already complete for {email}, returning existing user")
                return OnboardingCompleteResponse(
                    id=existing_user.id,
                    email=existing_user.email,
                    first_name=existing_user.first_name,
                    last_name=existing_user.last_name,
                    role=existing_user.role,
                    company_id=existing_user.company_id,
                    created_at=existing_user.created_at.isoformat() if hasattr(existing_user.created_at, 'isoformat') else str(existing_user.created_at)
                )

        # User exists but onboarding is incomplete - this is an error state
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email {email} already exists but onboarding is incomplete. Please contact support."
        )

    # Step 2: Upload documents to S3 (only after confirming no existing user)
    try:
        reference_doc_bytes = await reference_doc.read()

        # Generate S3 keys
        reference_s3_key = s3_service.generate_s3_key(
            prefix="user-onboarding-docs",
            filename=f"{email}_{reference_doc.filename}",
            extension=reference_doc.filename.split(".")[-1] if "." in reference_doc.filename else "pdf"
        )

        # Upload reference document to documents bucket
        reference_doc_url = await s3_service.upload_file(
            file_bytes=reference_doc_bytes,
            s3_key=reference_s3_key,
            content_type=reference_doc.content_type,
            bucket_type="documents"
        )
        uploaded_s3_keys.append((reference_s3_key, "documents"))

        # Handle CSR SOP document (optional)
        csr_sop_doc_url = None
        if csr_sop_doc and csr_sop_doc.filename:
            csr_sop_doc_bytes = await csr_sop_doc.read()
            csr_sop_s3_key = s3_service.generate_s3_key(
                prefix="user-onboarding-docs",
                filename=f"{email}_csr_{csr_sop_doc.filename}",
                extension=csr_sop_doc.filename.split(".")[-1] if "." in csr_sop_doc.filename else "pdf"
            )
            csr_sop_doc_url = await s3_service.upload_file(
                file_bytes=csr_sop_doc_bytes,
                s3_key=csr_sop_s3_key,
                content_type=csr_sop_doc.content_type,
                bucket_type="documents"
            )
            uploaded_s3_keys.append((csr_sop_s3_key, "documents"))

        # Handle Sales SOP document (optional)
        sales_sop_doc_url = None
        if sales_sop_doc and sales_sop_doc.filename:
            sales_sop_doc_bytes = await sales_sop_doc.read()
            sales_sop_s3_key = s3_service.generate_s3_key(
                prefix="user-onboarding-docs",
                filename=f"{email}_sales_{sales_sop_doc.filename}",
                extension=sales_sop_doc.filename.split(".")[-1] if "." in sales_sop_doc.filename else "pdf"
            )
            sales_sop_doc_url = await s3_service.upload_file(
                file_bytes=sales_sop_doc_bytes,
                s3_key=sales_sop_s3_key,
                content_type=sales_sop_doc.content_type,
                bucket_type="documents"
            )
            uploaded_s3_keys.append((sales_sop_s3_key, "documents"))

        logger.info(f"Uploaded documents to S3 for {email}")

        # Step 3: Create all database records in transaction
        try:
            # Re-check user existence (in case another request created it between checks)
            existing_user_check = await user_repo.get_by_email(email)
            if existing_user_check:
                # Another request completed onboarding - clean up S3 and return existing user
                await _cleanup_s3_files(s3_service, uploaded_s3_keys)

                if existing_user_check.company_id:
                    existing_company = await company_service.get_company_by_id(existing_user_check.company_id)
                    if existing_company:
                        logger.info(f"Onboarding completed by another request for {email}, returning existing user")
                        return OnboardingCompleteResponse(
                            id=existing_user_check.id,
                            email=existing_user_check.email,
                            first_name=existing_user_check.first_name,
                            last_name=existing_user_check.last_name,
                            role=existing_user_check.role,
                            company_id=existing_user_check.company_id,
                            created_at=existing_user_check.created_at.isoformat() if hasattr(existing_user_check.created_at, 'isoformat') else str(existing_user_check.created_at)
                        )

                # Fallback - shouldn't happen, but handle gracefully
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Unexpected state during idempotent onboarding check for {email}"
                )

            # Build extra_metadata with any existing metadata
            extra_metadata = {}
            if crm_company_id:
                extra_metadata["crm_company_id"] = crm_company_id
            if ghost_mode_enabled:
                extra_metadata["ghost_mode_enabled"] = True

            # Create Company with all fields
            company_orm = await company_service.create_company(
                name=companyName,
                phone_number=phone_number,
                address=address,
                reference_doc_url=reference_doc_url,
                csr_sop_doc_url=csr_sop_doc_url,
                sales_sop_doc_url=sales_sop_doc_url,
                extra_metadata=extra_metadata if extra_metadata else None
            )
            company_id = company_orm.id

            # Create CompanyIntegration (only if integration data is provided)
            # The service will handle the logic of whether to create or not
            await company_service.create_company_integration(
                company_id=company_id,
                location_id=location_id,
                crm_provider=crm_provider,
                crm_api_key=crm_api_key,
                crm_company_id=crm_company_id,
                voip_provider=voip_provider,
                voip_api_key=voip_api_key,
                voip_company_id=voip_company_id,
                st_tenant_id=st_tenant_id,
                st_client_id=st_client_id,
                st_client_secret=st_client_secret,
            )

            # Hash password
            password_hash = get_password_hash(password)

            # Create User
            user_orm = UserORM(
                email=email,
                password_hash=password_hash,
                role=UserRole.EXECUTIVE.value,  # Default to EXECUTIVE for company owners
                first_name=firstName,
                last_name=lastName,
                company_id=company_id,
                is_active=True,
            )
            db.add(user_orm)
            await db.flush()
            await db.refresh(user_orm)

            # Commit all changes atomically
            await db.commit()

            # Convert to domain model for response
            user = user_repo._to_domain(user_orm)

            logger.info(f"Created user {email} with company {companyName}")

            # Schedule background tasks to upload SOP documents to Shoonya
            if csr_sop_doc_url:
                background_tasks.add_task(
                    _upload_sop_to_shoonya,
                    s3_url=csr_sop_doc_url,
                    company_id=str(company_id),
                    sop_name="CSR SOP",
                    target_role="csr"
                )
            if sales_sop_doc_url:
                background_tasks.add_task(
                    _upload_sop_to_shoonya,
                    s3_url=sales_sop_doc_url,
                    company_id=str(company_id),
                    sop_name="Sales SOP",
                    target_role="sales_rep"
                )

            return OnboardingCompleteResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role,
                company_id=user.company_id,
                created_at=user.created_at.isoformat() if hasattr(user.created_at, 'isoformat') else str(user.created_at)
            )

        except HTTPException:
            # HTTPException during DB operations - rollback and cleanup
            await db.rollback()
            if uploaded_s3_keys and s3_service:
                await _cleanup_s3_files(s3_service, uploaded_s3_keys)
            raise
        except Exception as e:
            # Database error - rollback transaction
            await db.rollback()
            # Cleanup S3 files
            if uploaded_s3_keys and s3_service:
                await _cleanup_s3_files(s3_service, uploaded_s3_keys)
            logger.error(f"Database error during onboarding: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error during onboarding: {str(e)}"
            )

    except HTTPException:
        # HTTPExceptions should not trigger S3 cleanup - they're validation errors
        # Only cleanup if we uploaded files
        if uploaded_s3_keys and s3_service:
            await _cleanup_s3_files(s3_service, uploaded_s3_keys)
        raise
    except PermissionError as e:
        # Cleanup S3 files on permission error
        if uploaded_s3_keys and s3_service:
            await _cleanup_s3_files(s3_service, uploaded_s3_keys)

        logger.error(f"S3 permission error during onboarding: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"S3 access error: {str(e)}. Please check AWS credentials and bucket permissions."
        )
    except Exception as e:
        # Cleanup S3 files on error
        if uploaded_s3_keys and s3_service:
            await _cleanup_s3_files(s3_service, uploaded_s3_keys)

        logger.error(f"Error completing onboarding: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error completing onboarding: {str(e)}"
        )

async def _cleanup_s3_files(s3_service, uploaded_keys: list[tuple[str, str]]) -> None:
    """
    Clean up uploaded S3 files.

    Args:
        s3_service: S3 service instance
        uploaded_keys: List of tuples (s3_key, bucket_type) to delete
    """
    for s3_key, bucket_type in uploaded_keys:
        try:
            await s3_service.delete_file(s3_key, bucket_type)
            logger.info(f"Cleaned up S3 file: {s3_key}")
        except Exception as e:
            logger.warning(f"Failed to cleanup S3 file {s3_key}: {e}")


async def _upload_sop_to_shoonya(
    s3_url: str,
    company_id: str,
    sop_name: str,
    target_role: str | None = None,
) -> None:
    """
    Background task to upload SOP document from S3 to Shoonya.

    Uploads directly from S3 URL to Shoonya without downloading the file locally.

    Args:
        s3_url: S3 URL of the SOP document (HTTPS URL)
        company_id: Company ID
        sop_name: Name of the SOP
        target_role: Target role (csr, sales_rep, or None for company-wide)
                    Note: "csr" will be mapped to "customer_rep" for the API
    """
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            logger.warning(f"Shoonya not available, skipping SOP upload for {sop_name}")
            return

        # Map target_role to API format
        # API expects "customer_rep" for CSR phone call SOPs, "sales_rep" for sales meeting SOPs
        api_target_role = None
        if target_role == "csr":
            api_target_role = "customer_rep"
        elif target_role == "sales_rep":
            api_target_role = "sales_rep"
        elif target_role:
            # Pass through other roles as-is
            api_target_role = target_role

        # Upload directly from S3 URL to Shoonya
        result = await shoonya.upload_sop_document(
            file_url=s3_url,
            company_id=company_id,
            sop_name=sop_name,
            target_role=api_target_role,
        )

        logger.info(
            f"Successfully uploaded SOP to Shoonya",
            sop_name=sop_name,
            company_id=company_id,
            job_id=result.get("job_id"),
        )

    except Exception as e:
        logger.error(
            f"Error uploading SOP to Shoonya: {e}",
            sop_name=sop_name,
            company_id=company_id,
            exc_info=True,
        )
