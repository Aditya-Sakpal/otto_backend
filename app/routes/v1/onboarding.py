"""
Onboarding API routes.

Handles user/company creation, GHL integration, and document storage.
"""
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from pydantic import EmailStr

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
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
from app.domain.users.schemas import UserResponse
from app.services.ghl_service import GHLService
from app.services.ctm_service import CTMService
from app.services.onboarding_service import OnboardingService
from app.infrastructure.integrations.servicetitan import ServiceTitanClient

logger = get_logger(__name__)

router = APIRouter()

RESPONSES = {
    401: {"description": "Invalid credentials"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


# ---------------------------------------------------------------------------
# Validation endpoints (pre-submission)
# ---------------------------------------------------------------------------


@router.post("/validate-ghl", response_model=ValidateGHLResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_ghl(body: ValidateGHLRequest) -> ValidateGHLResponse:
    """Verify GoHighLevel credentials before final submission."""
    try:
        result = await GHLService.verify_api_key(body.api_key, body.location_id)
        if not result:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GHL API key or location ID")
        return ValidateGHLResponse(company_id=result["company_id"], company_name=result["company_name"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating GHL credentials: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error validating GHL credentials: {str(e)}")


@router.post("/validate-ctm", response_model=ValidateCTMResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_ctm(body: ValidateCTMRequest) -> ValidateCTMResponse:
    """Verify Call Tracking Metrics (CTM) credentials before final submission."""
    try:
        result = await CTMService.verify_api_key(body.access_key, body.secret_key)
        if not result:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CTM access key or secret key")
        return ValidateCTMResponse(secret_key=result["secret_key"], company_name=result["company_name"], company_id=result["company_id"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating CTM credentials: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error validating CTM credentials: {str(e)}")


@router.post("/validate-servicetitan", response_model=ValidateServiceTitanResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def validate_servicetitan(body: ValidateServiceTitanRequest) -> ValidateServiceTitanResponse:
    """Verify ServiceTitan credentials before final submission."""
    try:
        client = ServiceTitanClient(tenant_id=body.tenant_id, client_id=body.client_id, client_secret=body.client_secret)
        result = await client.verify_credentials()
        return ValidateServiceTitanResponse(tenant_id=result["tenant_id"], status=result["status"])
    except Exception as e:
        logger.error(f"Error validating ServiceTitan credentials: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid ServiceTitan credentials: {str(e)}")


# ---------------------------------------------------------------------------
# Main onboarding completion
# ---------------------------------------------------------------------------


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
    csr_sop_doc: UploadFile | None = File(None),
    sales_sop_doc: UploadFile | None = File(None),
    phone_number: str | None = Form(None),
    address: str | None = Form(None),
    location_id: str | None = Form(None),
    crm_provider: str | None = Form(None),
    crm_api_key: str | None = Form(None),
    crm_company_id: str | None = Form(None),
    voip_provider: str | None = Form(None),
    voip_api_key: str | None = Form(None),
    voip_access_key: str | None = Form(None),
    voip_company_id: str | None = Form(None),
    st_tenant_id: str | None = Form(None),
    st_client_id: str | None = Form(None),
    st_client_secret: str | None = Form(None),
    ghost_mode_enabled: bool = Form(False),
) -> OnboardingCompleteResponse:
    """
    Complete onboarding: create user, company, integration, tenant config, and return JWT.

    Idempotent — returns existing user with fresh tokens if already onboarded.
    """
    if not reference_doc.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reference_doc file is required")

    s3_service = get_s3_service()
    if not s3_service:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="S3 service is not configured")

    try:
        service = OnboardingService(db)
        result = await service.complete_onboarding(
            first_name=firstName,
            last_name=lastName,
            email=email,
            password=password,
            company_name=companyName,
            s3_service=s3_service,
            reference_doc=reference_doc,
            csr_sop_doc=csr_sop_doc,
            sales_sop_doc=sales_sop_doc,
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

        # Schedule background Shoonya SOP uploads for new users only
        if not result.is_existing:
            if result.csr_sop_doc_url:
                background_tasks.add_task(
                    _upload_sop_to_shoonya,
                    s3_url=result.csr_sop_doc_url,
                    company_id=str(result.company_id),
                    sop_name="CSR SOP",
                    target_role="csr",
                )
            if result.sales_sop_doc_url:
                background_tasks.add_task(
                    _upload_sop_to_shoonya,
                    s3_url=result.sales_sop_doc_url,
                    company_id=str(result.company_id),
                    sop_name="Sales SOP",
                    target_role="sales_rep",
                )

        user = result.user
        return OnboardingCompleteResponse(
            access_token=result.access_token,
            refresh_token=result.refresh_token,
            user=UserResponse(
                id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                role=user.role,
                company_id=user.company_id,
                is_active=user.is_active,
                created_at=user.created_at,
            ),
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error completing onboarding: {str(e)}")


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------


async def _upload_sop_to_shoonya(
    s3_url: str,
    company_id: str,
    sop_name: str,
    target_role: str | None = None,
) -> None:
    """Background task to upload SOP document from S3 to Shoonya."""
    try:
        shoonya = get_shoonya_client()
        if not shoonya.is_available():
            logger.warning(f"Shoonya not available, skipping SOP upload for {sop_name}")
            return

        api_target_role = None
        if target_role == "csr":
            api_target_role = "customer_rep"
        elif target_role == "sales_rep":
            api_target_role = "sales_rep"
        elif target_role:
            api_target_role = target_role

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
