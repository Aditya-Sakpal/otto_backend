"""
Onboarding API routes.

Handles user/company creation, GHL integration, and document storage.
"""
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from pydantic import EmailStr

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
from app.core.encryption import encrypt_api_key
from app.core.security import get_password_hash
from app.domain.schemas.onboarding import (
    OnboardingCompleteResponse,
    ValidateGHLRequest,
    ValidateGHLResponse,
    ValidateCTMRequest,
    ValidateCTMResponse,
)
from app.services.ghl_service import GHLService
from app.services.ctm_service import CTMService
from app.domain.users.repository import UserRepository
from app.infrastructure.database.models.company import CompanyORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM
from app.domain.enums import UserRole

logger = get_logger(__name__)

router = APIRouter()


@router.post("/validate-ghl", response_model=ValidateGHLResponse, status_code=status.HTTP_200_OK)
async def validate_ghl(
    request: ValidateGHLRequest,
) -> ValidateGHLResponse:
    """
    Verify GoHighLevel credentials before final submission.

    Args:
        request: Validation request with location_id and api_key

    Returns:
        GHL company information if valid

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    try:
        result = await GHLService.verify_api_key(request.api_key, request.location_id)

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


@router.post("/validate-ctm", response_model=ValidateCTMResponse, status_code=status.HTTP_200_OK)
async def validate_ctm(
    request: ValidateCTMRequest,
) -> ValidateCTMResponse:
    """
    Verify Call Tracking Metrics (CTM) credentials before final submission.

    Args:
        request: Validation request with access_key and secret_key

    Returns:
        CTM company information if valid (secret_key, company_name, company_id)

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    try:
        result = await CTMService.verify_api_key(request.access_key, request.secret_key)

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


@router.post("/complete", response_model=OnboardingCompleteResponse, status_code=status.HTTP_201_CREATED)
async def complete_onboarding(
    db: DbSession,
    firstName: str = Form(...),
    lastName: str = Form(...),
    email: EmailStr = Form(...),
    password: str = Form(...),
    companyName: str = Form(...),
    location_id: str = Form(...),
    crm_provider: str = Form(...),
    crm_api_key: str = Form(...),
    crm_company_id: str = Form(...),
    voip_provider: str = Form(...),
    voip_api_key: str = Form(...),
    voip_company_id: str = Form(...),
    reference_doc: UploadFile = File(...),
    sop_doc: UploadFile = File(...),
) -> OnboardingCompleteResponse:
    """
    Complete onboarding: create user, company, integration, and upload documents.

    This endpoint performs an atomic operation:
    1. Validates all fields and files
    2. Uploads documents to S3
    3. Creates Company, User, and CompanyIntegration records in a transaction

    Args:
        firstName: User's first name
        lastName: User's last name
        email: User's email address
        password: User's password
        companyName: Company name
        location_id: GHL location ID
        api_key: GHL API key (will be encrypted)
        ghl_company_id: GHL company ID
        reference_doc: Reference document file
        sop_doc: SOP document file
        db: Database session

    Returns:
        Created user information (excluding password)

    Raises:
        HTTPException: 400 if validation fails, 500 if creation fails
    """
    # Validate that files are present
    if not reference_doc.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reference_doc file is required"
        )
    if not sop_doc.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sop_doc file is required"
        )

    # Get S3 service
    s3_service = get_s3_service()
    if not s3_service:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3 service is not configured"
        )

    # Track uploaded S3 keys for cleanup on failure
    uploaded_keys = []

    try:
        # Step 1: Upload documents to S3
        reference_doc_bytes = await reference_doc.read()
        sop_doc_bytes = await sop_doc.read()

        # Generate S3 keys
        reference_s3_key = s3_service.generate_s3_key(
            prefix="user-onboarding-docs",
            filename=f"{email}_{reference_doc.filename}",
            extension=reference_doc.filename.split(".")[-1] if "." in reference_doc.filename else "pdf"
        )
        sop_s3_key = s3_service.generate_s3_key(
            prefix="user-onboarding-docs",
            filename=f"{email}_{sop_doc.filename}",
            extension=sop_doc.filename.split(".")[-1] if "." in sop_doc.filename else "pdf"
        )

        # Upload files to documents bucket
        # Note: upload_file is async, so we await it directly
        reference_doc_url = await s3_service.upload_file(
            file_bytes=reference_doc_bytes,
            s3_key=reference_s3_key,
            content_type=reference_doc.content_type,
            bucket_type="documents"
        )
        uploaded_keys.append(reference_s3_key)

        sop_doc_url = await s3_service.upload_file(
            file_bytes=sop_doc_bytes,
            s3_key=sop_s3_key,
            content_type=sop_doc.content_type,
            bucket_type="documents"
        )
        uploaded_keys.append(sop_s3_key)

        logger.info(f"Uploaded documents to S3 for {email}")

        # Step 2: Database transaction - create Company, User, and CompanyIntegration
        async with db.begin():
            # Check if user already exists
            user_repo = UserRepository(db)
            existing_user = await user_repo.get_by_email(email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User with email {email} already exists"
                )

            # Create Company
            company_orm = CompanyORM(
                name=companyName,
                reference_doc_url=reference_doc_url,
                sop_doc_url=sop_doc_url,
                extra_metadata={"crm_company_id": crm_company_id}
            )
            db.add(company_orm)
            await db.flush()
            await db.refresh(company_orm)
            company_id = company_orm.id

            # Encrypt API key
            crm_encrypted_api_key = encrypt_api_key(crm_api_key)
            voip_encrypted_api_key = encrypt_api_key(voip_api_key)


            # Create CompanyIntegration
            integration_orm = CompanyIntegrationORM(
                company_id=company_id,
                location_id=location_id,
                crm_api_encrypted_key=crm_encrypted_api_key,
                crm_provider=crm_provider,
                crm_company_id=crm_company_id,
                voip_api_encrypted_key=voip_encrypted_api_key,
                voip_provider=voip_provider,
                voip_company_id= voip_company_id
            )
            db.add(integration_orm)
            await db.flush()

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

            # Convert to domain model for response
            user = user_repo._to_domain(user_orm)

            logger.info(f"Created user {email} with company {companyName}")

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
        # Cleanup S3 files on validation failure
        if uploaded_keys and s3_service:
            # For now, we log the keys that should be cleaned up
            logger.warning(f"S3 files uploaded but transaction failed. Keys to cleanup: {uploaded_keys}")
        raise
    except Exception as e:
        # Cleanup S3 files on error
        if uploaded_keys and s3_service:
            logger.warning(f"S3 files uploaded but transaction failed. Keys to cleanup: {uploaded_keys}")

        logger.error(f"Error completing onboarding: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error completing onboarding: {str(e)}"
        )
