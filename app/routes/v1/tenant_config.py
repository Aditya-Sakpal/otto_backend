"""
Tenant Configuration API routes.

Provides endpoints for managing tenant-specific configurations
by proxying to Shunya's tenant-config API and storing locally.
"""
import traceback
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession
from app.core.permissions import require_executive
from app.core.logging import get_logger
from app.domain.users.models import User
from app.domain.schemas.tenant_config import (
    TenantConfigCreateRequest,
    TenantConfigUpdateRequest,
    TenantConfigResponse,
)
from app.services.tenant_config_service import TenantConfigService

router = APIRouter()
logger = get_logger(__name__)

RESPONSES = {
    400: {"description": "Bad request"},
    403: {"description": "Forbidden"},
    404: {"description": "Resource not found"},
    409: {"description": "Conflict - config already exists"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}


@router.post("", response_model=TenantConfigResponse, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def create_tenant_config(
    request: TenantConfigCreateRequest,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Create a new tenant configuration.

    Calls Shunya's tenant-config API and stores the configuration locally.

    - **company_id**: Company UUID
    - **company_name**: Display name of the company
    """
    try:
        service = TenantConfigService(db)
        config = await service.create_config(
            company_id=request.company_id,
            company_name=request.company_name,
            qualification_thresholds=request.qualification_thresholds,
            service_prioritization=request.service_prioritization,
            custom_keywords=request.custom_keywords,
            qualification_rules=request.qualification_rules,
            business_hours=request.business_hours,
            service_area=request.service_area,
            industry=request.industry,
            primary_services=request.primary_services,
        )
        return TenantConfigResponse.model_validate(config)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tenant config: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{company_id}", response_model=TenantConfigResponse, responses=RESPONSES)
async def get_tenant_config(
    company_id: UUID,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Get tenant configuration for a company.

    First checks our local DB, then falls back to Shunya API.

    - **company_id**: Company UUID
    """
    try:
        service = TenantConfigService(db)
        config = await service.get_config_with_shunya_fallback(company_id)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for company {company_id} not found",
            )

        return TenantConfigResponse.model_validate(config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tenant config: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/{company_id}", response_model=TenantConfigResponse, responses=RESPONSES)
async def update_tenant_config(
    company_id: UUID,
    request: TenantConfigUpdateRequest,
    db: DbSession,
    current_user: User = Depends(require_executive),
):
    """
    Update tenant configuration for a company.

    - **company_id**: Company UUID
    """
    try:
        # Build updates from non-None fields
        updates = request.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No updates provided",
            )

        service = TenantConfigService(db)
        config = await service.update_config(company_id, updates)

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration for company {company_id} not found",
            )

        return TenantConfigResponse.model_validate(config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tenant config: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
