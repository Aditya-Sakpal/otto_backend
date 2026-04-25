"""
Settings API routes.

Provides endpoints for managing company integrations and documents.
"""
import traceback
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.core.dependencies import DbSession
from app.core.permissions import require_executive
from app.core.logging import get_logger
from app.core.s3 import get_s3_service
from app.domain.users.models import User
from app.domain.schemas.settings import (
    IntegrationResponse,
    IntegrationsListResponse,
    DocumentResponse,
    DocumentsListResponse,
    UpdateIntegrationRequest,
    CreateIntegrationRequest,
    UpdateDocumentRequest,
    SettingsResponse,
    FollowUpManualReviewPatch,
)
from app.services.company_service import CompanyService

router = APIRouter()
logger = get_logger(__name__)

RESPONSES = {
    400: {"description": "Bad request"},
    403: {"description": "Forbidden"},
    404: {"description": "Resource not found"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}

# Document type mapping
DOCUMENT_TYPE_MAPPING = {
    "reference": "reference_doc_url",
    "sop": "sop_doc_url",
    "csr_sop": "csr_sop_doc_url",
    "sales_sop": "sales_sop_doc_url",
}

REVERSE_DOCUMENT_TYPE_MAPPING = {v: k for k, v in DOCUMENT_TYPE_MAPPING.items()}


def _crm_connected(integration) -> bool:
    """ServiceTitan uses st_client_secret_encrypted; all other CRMs use crm_api_encrypted_key."""
    if integration.crm_provider == "servicetitan":
        return bool(integration.st_client_secret_encrypted)
    return bool(integration.crm_api_encrypted_key)


@router.get("", response_model=SettingsResponse, responses=RESPONSES)
async def get_settings(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Get complete settings for a company (integrations and documents).

    - **company_id**: Company UUID

    Returns integrations, documents, and **follow_up_manual_review_enabled** (contextual follow-up draft-before-send).

    **Example response (200)** — shape only; lists may contain real integration/document objects:

    ```json
    {
      "id": "00000000-0000-4000-8000-000000000001",
      "created_at": "2026-03-27T12:00:00",
      "updated_at": null,
      "integrations": [],
      "documents": [],
      "follow_up_manual_review_enabled": false
    }
    ```

    Required role: EXECUTIVE
    """
    try:
        service = CompanyService(db)
        
        # Get integrations
        integration_orm = await service.get_company_integration(company_id)
        integrations = []
        
        if integration_orm:
            # Build CRM integration if exists
            if integration_orm.crm_provider:
                integrations.append(IntegrationResponse(
                    id=integration_orm.id,
                    company_id=integration_orm.company_id,
                    provider=integration_orm.crm_provider,
                    provider_type="crm",
                    status="connected" if integration_orm.crm_api_encrypted_key else "disconnected",
                    description=f"{integration_orm.crm_provider} CRM connection for lead and contact management",
                    last_sync=integration_orm.extra_metadata.get("crm_last_sync") if integration_orm.extra_metadata else None,
                    location_id=integration_orm.location_id,
                    company_id_external=integration_orm.crm_company_id,
                    extra_metadata=integration_orm.extra_metadata,
                ))
            
            # Build VoIP integration if exists
            if integration_orm.voip_provider:
                integrations.append(IntegrationResponse(
                    id=integration_orm.id,
                    company_id=integration_orm.company_id,
                    provider=integration_orm.voip_provider,
                    provider_type="voip",
                    status="connected" if integration_orm.voip_api_encrypted_key else "disconnected",
                    description=f"{integration_orm.voip_provider} phone system integration for call tracking and recording",
                    last_sync=integration_orm.extra_metadata.get("voip_last_sync") if integration_orm.extra_metadata else None,
                    location_id=integration_orm.location_id,
                    company_id_external=integration_orm.voip_company_id,
                    extra_metadata=integration_orm.extra_metadata,
                ))
        
        # Get documents
        company = await service.get_company_by_id(company_id)
        documents = []
        
        if company:
            # Refresh company to ensure we have latest data from database
            await db.refresh(company)
            
            # Get document metadata from extra_metadata
            doc_metadata = company.extra_metadata.get("documents", {}) if company.extra_metadata else {}
            
            # Debug logging - check actual attribute values
            logger.info(f"Company {company_id} documents check:")
            logger.info(f"  reference_doc_url: {repr(getattr(company, 'reference_doc_url', 'ATTRIBUTE_NOT_FOUND'))}")
            logger.info(f"  sop_doc_url: {repr(getattr(company, 'sop_doc_url', 'ATTRIBUTE_NOT_FOUND'))}")
            logger.info(f"  csr_sop_doc_url: {repr(getattr(company, 'csr_sop_doc_url', 'ATTRIBUTE_NOT_FOUND'))}")
            logger.info(f"  sales_sop_doc_url: {repr(getattr(company, 'sales_sop_doc_url', 'ATTRIBUTE_NOT_FOUND'))}")
            
            # Reference document
            ref_url = getattr(company, 'reference_doc_url', None)
            if ref_url:
                ref_meta = doc_metadata.get("reference", {})
                documents.append(DocumentResponse(
                    document_type="reference",
                    name=ref_meta.get("name", "Reference Document"),
                    url=ref_url,
                    type=ref_meta.get("type", "PDF"),
                    size=ref_meta.get("size"),
                    uploaded_at=ref_meta.get("uploaded_at"),
                    uploaded_by=ref_meta.get("uploaded_by"),
                ))
            
            # SOP document (legacy)
            sop_url = getattr(company, 'sop_doc_url', None)
            if sop_url:
                sop_meta = doc_metadata.get("sop", {})
                documents.append(DocumentResponse(
                    document_type="sop",
                    name=sop_meta.get("name", "SOP Document"),
                    url=sop_url,
                    type=sop_meta.get("type", "PDF"),
                    size=sop_meta.get("size"),
                    uploaded_at=sop_meta.get("uploaded_at"),
                    uploaded_by=sop_meta.get("uploaded_by"),
                ))
            
            # CSR SOP document
            csr_url = getattr(company, 'csr_sop_doc_url', None)
            if csr_url:
                csr_meta = doc_metadata.get("csr_sop", {})
                documents.append(DocumentResponse(
                    document_type="csr_sop",
                    name=csr_meta.get("name", "CSR SOP Document"),
                    url=csr_url,
                    type=csr_meta.get("type", "PDF"),
                    size=csr_meta.get("size"),
                    uploaded_at=csr_meta.get("uploaded_at"),
                    uploaded_by=csr_meta.get("uploaded_by"),
                ))
            
            # Sales SOP document
            sales_url = getattr(company, 'sales_sop_doc_url', None)
            if sales_url:
                sales_meta = doc_metadata.get("sales_sop", {})
                documents.append(DocumentResponse(
                    document_type="sales_sop",
                    name=sales_meta.get("name", "Sales SOP Document"),
                    url=sales_url,
                    type=sales_meta.get("type", "PDF"),
                    size=sales_meta.get("size"),
                    uploaded_at=sales_meta.get("uploaded_at"),
                    uploaded_by=sales_meta.get("uploaded_by"),
                ))
        
        follow_up_manual_review_enabled = (
            bool(company.follow_up_manual_review_enabled) if company else False
        )

        return SettingsResponse(
            integrations=integrations,
            documents=documents,
            follow_up_manual_review_enabled=follow_up_manual_review_enabled,
        )
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.patch(
    "/follow-up-manual-review",
    response_model=FollowUpManualReviewPatch,
    responses=RESPONSES,
)
async def patch_follow_up_manual_review(
    company_id: UUID = Query(..., description="Company UUID"),
    body: FollowUpManualReviewPatch = ...,
    db: DbSession = ...,
    current_user: User = Depends(require_executive),
):
    """
    Turn contextual follow-up manual review (draft before send) on or off for a company.

    **Example request body**

    ```json
    { "follow_up_manual_review_enabled": true }
    ```

    **Example response (200)**

    ```json
    {
      "id": "00000000-0000-4000-8000-000000000002",
      "created_at": "2026-03-27T12:00:00",
      "updated_at": null,
      "follow_up_manual_review_enabled": true
    }
    ```
    """
    try:
        service = CompanyService(db)
        company = await service.get_company_by_id(company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        updated = await service.update_company(
            company_id,
            follow_up_manual_review_enabled=body.follow_up_manual_review_enabled,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update company",
            )
        return FollowUpManualReviewPatch(
            follow_up_manual_review_enabled=body.follow_up_manual_review_enabled,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error patching follow-up manual review: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/integrations", response_model=IntegrationsListResponse, responses=RESPONSES)
async def get_integrations(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Get all integrations for a company.
    
    - **company_id**: Company UUID
    
    Returns list of CRM and VoIP integrations.
    
    Required role: EXECUTIVE
    """
    try:
        service = CompanyService(db)
        integration_orm = await service.get_company_integration(company_id)
        integrations = []
        
        if integration_orm:
            # Build CRM integration if exists
            if integration_orm.crm_provider:
                integrations.append(IntegrationResponse(
                    id=integration_orm.id,
                    company_id=integration_orm.company_id,
                    provider=integration_orm.crm_provider,
                    provider_type="crm",
                    status="connected" if _crm_connected(integration_orm) else "disconnected",
                    description=f"{integration_orm.crm_provider} CRM connection for lead and contact management",
                    last_sync=integration_orm.extra_metadata.get("crm_last_sync") if integration_orm.extra_metadata else None,
                    location_id=integration_orm.location_id,
                    company_id_external=integration_orm.crm_company_id,
                    extra_metadata=integration_orm.extra_metadata,
                ))

            # Build VoIP integration if exists
            if integration_orm.voip_provider:
                integrations.append(IntegrationResponse(
                    id=integration_orm.id,
                    company_id=integration_orm.company_id,
                    provider=integration_orm.voip_provider,
                    provider_type="voip",
                    status="connected" if integration_orm.voip_api_encrypted_key else "disconnected",
                    description=f"{integration_orm.voip_provider} phone system integration for call tracking and recording",
                    last_sync=integration_orm.extra_metadata.get("voip_last_sync") if integration_orm.extra_metadata else None,
                    location_id=integration_orm.location_id,
                    company_id_external=integration_orm.voip_company_id,
                    extra_metadata=integration_orm.extra_metadata,
                ))

        return IntegrationsListResponse(
            integrations=integrations,
            total_count=len(integrations),
        )
    except Exception as e:
        logger.error(f"Error getting integrations: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/integrations/{integration_id}", response_model=IntegrationResponse, responses=RESPONSES)
async def get_integration(
    integration_id: UUID,
    company_id: UUID,
    db: DbSession,
    provider_type: str = Query(..., description="Integration type: 'crm' or 'voip'"),
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Get integration details by ID.
    
    - **integration_id**: Integration UUID
    - **company_id**: Company UUID
    - **provider_type**: Integration type ('crm' or 'voip')
    
    Required role: EXECUTIVE
    """
    try:
        if provider_type not in ["crm", "voip"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="provider_type must be 'crm' or 'voip'",
            )
        
        service = CompanyService(db)
        from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
        integration_repo = CompanyIntegrationRepository(db)
        integration_orm = await integration_repo.get_by_id(integration_id)
        
        if not integration_orm or integration_orm.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found",
            )
        
        # Get the requested provider type
        if provider_type == "crm":
            if not integration_orm.crm_provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="CRM integration not found",
                )
            provider = integration_orm.crm_provider
            company_id_external = integration_orm.crm_company_id
            is_connected = _crm_connected(integration_orm)
        else:  # voip
            if not integration_orm.voip_provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="VoIP integration not found",
                )
            provider = integration_orm.voip_provider
            company_id_external = integration_orm.voip_company_id
            is_connected = bool(integration_orm.voip_api_encrypted_key)
        
        return IntegrationResponse(
            id=integration_orm.id,
            company_id=integration_orm.company_id,
            provider=provider,
            provider_type=provider_type,
            status="connected" if is_connected else "disconnected",
            description=f"{provider} {'CRM' if provider_type == 'crm' else 'phone system'} integration for {'lead and contact management' if provider_type == 'crm' else 'call tracking and recording'}",
            last_sync=integration_orm.extra_metadata.get(f"{provider_type}_last_sync") if integration_orm.extra_metadata else None,
            location_id=integration_orm.location_id,
            company_id_external=company_id_external,
            extra_metadata=integration_orm.extra_metadata,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting integration: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/integrations", response_model=List[IntegrationResponse], status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def create_integration(
    company_id: UUID,
    request: CreateIntegrationRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Create a new integration for a company.
    
    - **company_id**: Company UUID
    
    Returns list of created integrations (CRM and/or VoIP).
    
    Required role: EXECUTIVE
    """
    try:
        service = CompanyService(db)
        integration_orm = await service.upsert_company_integration(
            company_id=company_id,
            location_id=request.location_id,
            crm_provider=request.crm_provider,
            crm_api_key=request.crm_api_key,
            crm_company_id=request.crm_company_id,
            voip_provider=request.voip_provider,
            voip_api_key=request.voip_api_key,
            voip_company_id=request.voip_company_id,
            extra_metadata=request.extra_metadata,
        )
        
        # Return all created integrations
        integrations = []
        if integration_orm.crm_provider:
            integrations.append(IntegrationResponse(
                id=integration_orm.id,
                company_id=integration_orm.company_id,
                provider=integration_orm.crm_provider,
                provider_type="crm",
                status="connected" if integration_orm.crm_api_encrypted_key else "disconnected",
                description=f"{integration_orm.crm_provider} CRM connection for lead and contact management",
                last_sync=None,
                location_id=integration_orm.location_id,
                company_id_external=integration_orm.crm_company_id,
                extra_metadata=integration_orm.extra_metadata,
            ))
        
        if integration_orm.voip_provider:
            integrations.append(IntegrationResponse(
                id=integration_orm.id,
                company_id=integration_orm.company_id,
                provider=integration_orm.voip_provider,
                provider_type="voip",
                status="connected" if integration_orm.voip_api_encrypted_key else "disconnected",
                description=f"{integration_orm.voip_provider} phone system integration for call tracking and recording",
                last_sync=None,
                location_id=integration_orm.location_id,
                company_id_external=integration_orm.voip_company_id,
                extra_metadata=integration_orm.extra_metadata,
            ))
        
        return integrations
    except Exception as e:
        logger.error(f"Error creating integration: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/integrations/{integration_id}", response_model=List[IntegrationResponse], responses=RESPONSES)
async def update_integration(
    integration_id: UUID,
    company_id: UUID,
    request: UpdateIntegrationRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Update/configure an existing integration.
    
    - **integration_id**: Integration UUID
    - **company_id**: Company UUID
    
    Returns list of updated integrations (CRM and/or VoIP).
    
    Required role: EXECUTIVE
    """
    try:
        service = CompanyService(db)
        from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
        integration_repo = CompanyIntegrationRepository(db)
        integration_orm = await integration_repo.get_by_id(integration_id)
        
        if not integration_orm or integration_orm.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found",
            )
        
        updated_integration = await service.update_company_integration(
            company_id=company_id,
            location_id=request.location_id,
            crm_provider=request.crm_provider,
            crm_api_key=request.crm_api_key,
            crm_company_id=request.crm_company_id,
            voip_provider=request.voip_provider,
            voip_api_key=request.voip_api_key,
            voip_company_id=request.voip_company_id,
            extra_metadata=request.extra_metadata,
            st_tenant_id=request.st_tenant_id,
            st_client_id=request.st_client_id,
            st_client_secret=request.st_client_secret,
        )
        
        if not updated_integration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found",
            )
        
        # Return all integrations
        integrations = []
        if updated_integration.crm_provider:
            integrations.append(IntegrationResponse(
                id=updated_integration.id,
                company_id=updated_integration.company_id,
                provider=updated_integration.crm_provider,
                provider_type="crm",
                status="connected" if _crm_connected(updated_integration) else "disconnected",
                description=f"{updated_integration.crm_provider} CRM connection for lead and contact management",
                last_sync=updated_integration.extra_metadata.get("crm_last_sync") if updated_integration.extra_metadata else None,
                location_id=updated_integration.location_id,
                company_id_external=updated_integration.crm_company_id,
                extra_metadata=updated_integration.extra_metadata,
            ))
        
        if updated_integration.voip_provider:
            integrations.append(IntegrationResponse(
                id=updated_integration.id,
                company_id=updated_integration.company_id,
                provider=updated_integration.voip_provider,
                provider_type="voip",
                status="connected" if updated_integration.voip_api_encrypted_key else "disconnected",
                description=f"{updated_integration.voip_provider} phone system integration for call tracking and recording",
                last_sync=updated_integration.extra_metadata.get("voip_last_sync") if updated_integration.extra_metadata else None,
                location_id=updated_integration.location_id,
                company_id_external=updated_integration.voip_company_id,
                extra_metadata=updated_integration.extra_metadata,
            ))
        
        return integrations
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating integration: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/integrations/{integration_id}/logs", responses=RESPONSES)
async def get_integration_logs(
    integration_id: UUID,
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
    limit: int = Query(50, ge=1, le=100, description="Maximum number of log entries"),
):
    """
    Get integration logs.
    
    - **integration_id**: Integration UUID
    - **company_id**: Company UUID
    - **limit**: Maximum number of log entries (default: 50, max: 100)
    
    Returns logs stored in integration's extra_metadata.
    
    Required role: EXECUTIVE
    """
    try:
        from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository
        integration_repo = CompanyIntegrationRepository(db)
        integration_orm = await integration_repo.get_by_id(integration_id)
        
        if not integration_orm or integration_orm.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Integration not found",
            )
        
        # Get logs from extra_metadata
        logs = []
        if integration_orm.extra_metadata and "logs" in integration_orm.extra_metadata:
            logs = integration_orm.extra_metadata["logs"][:limit]
        
        return {
            "integration_id": str(integration_id),
            "logs": logs,
            "total_count": len(logs),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting integration logs: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/documents", response_model=DocumentsListResponse, responses=RESPONSES)
async def get_documents(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Get all documents for a company.
    
    - **company_id**: Company UUID
    
    Returns list of documents (reference, SOP, CSR SOP, Sales SOP).
    
    Required role: EXECUTIVE
    """
    try:
        service = CompanyService(db)
        company = await service.get_company_by_id(company_id)
        
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        
        documents = []
        doc_metadata = company.extra_metadata.get("documents", {}) if company.extra_metadata else {}
        
        # Reference document
        if company.reference_doc_url:
            ref_meta = doc_metadata.get("reference", {})
            documents.append(DocumentResponse(
                document_type="reference",
                name=ref_meta.get("name", "Reference Document"),
                url=company.reference_doc_url,
                type=ref_meta.get("type", "PDF"),
                size=ref_meta.get("size"),
                uploaded_at=ref_meta.get("uploaded_at"),
                uploaded_by=ref_meta.get("uploaded_by"),
            ))
        
        # SOP document (legacy)
        if company.sop_doc_url:
            sop_meta = doc_metadata.get("sop", {})
            documents.append(DocumentResponse(
                document_type="sop",
                name=sop_meta.get("name", "SOP Document"),
                url=company.sop_doc_url,
                type=sop_meta.get("type", "PDF"),
                size=sop_meta.get("size"),
                uploaded_at=sop_meta.get("uploaded_at"),
                uploaded_by=sop_meta.get("uploaded_by"),
            ))
        
        # CSR SOP document
        if company.csr_sop_doc_url:
            csr_meta = doc_metadata.get("csr_sop", {})
            documents.append(DocumentResponse(
                document_type="csr_sop",
                name=csr_meta.get("name", "CSR SOP Document"),
                url=company.csr_sop_doc_url,
                type=csr_meta.get("type", "PDF"),
                size=csr_meta.get("size"),
                uploaded_at=csr_meta.get("uploaded_at"),
                uploaded_by=csr_meta.get("uploaded_by"),
            ))
        
        # Sales SOP document
        if company.sales_sop_doc_url:
            sales_meta = doc_metadata.get("sales_sop", {})
            documents.append(DocumentResponse(
                document_type="sales_sop",
                name=sales_meta.get("name", "Sales SOP Document"),
                url=company.sales_sop_doc_url,
                type=sales_meta.get("type", "PDF"),
                size=sales_meta.get("size"),
                uploaded_at=sales_meta.get("uploaded_at"),
                uploaded_by=sales_meta.get("uploaded_by"),
            ))
        
        return DocumentsListResponse(
            documents=documents,
            total_count=len(documents),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting documents: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED, responses=RESPONSES)
async def upload_document(
    company_id: UUID,
    db: DbSession,
    document_type: str = Form(..., description="Document type: 'reference', 'csr_sop', 'sales_sop'"),
    file: UploadFile = File(...),
    name: Optional[str] = Form(None, description="Document name (optional, defaults to filename)"),
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Upload a new document.
    
    - **company_id**: Company UUID
    - **document_type**: Document type ('reference', 'sop', 'csr_sop', 'sales_sop')
    - **file**: Document file to upload
    - **name**: Optional document name (defaults to filename)
    
    Required role: EXECUTIVE
    """
    try:
        if document_type not in DOCUMENT_TYPE_MAPPING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type. Must be one of: {list(DOCUMENT_TYPE_MAPPING.keys())}",
            )
        
        # Get S3 service
        s3_service = get_s3_service()
        if not s3_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 service not available",
            )
        
        # Read file
        file_bytes = await file.read()
        file_size = len(file_bytes)
        
        # Determine file type from content type or extension
        content_type = file.content_type or "application/pdf"
        file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else "pdf"
        file_type_map = {
            "pdf": "PDF",
            "doc": "DOCX",
            "docx": "DOCX",
            "txt": "TXT",
        }
        doc_type = file_type_map.get(file_extension, "PDF")
        
        # Generate S3 key
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        s3_key = s3_service.generate_s3_key(
            prefix=f"company-documents/{company_id}",
            filename=f"{document_type}_{timestamp}_{file.filename or 'document'}",
            extension=file_extension,
        )
        
        # Upload to S3
        doc_url = await s3_service.upload_file(
            file_bytes=file_bytes,
            s3_key=s3_key,
            content_type=content_type,
            bucket_type="documents",
            metadata={
                "company_id": str(company_id),
                "document_type": document_type,
                "uploaded_by": f"{current_user.first_name} {current_user.last_name}".strip() if current_user else "System",
                "uploaded_at": datetime.utcnow().isoformat(),
            },
        )
        
        # Format file size
        size_str = f"{file_size / 1024 / 1024:.1f} MB" if file_size > 1024 * 1024 else f"{file_size / 1024:.0f} KB"
        
        # Update company document URL and metadata
        service = CompanyService(db)
        company = await service.get_company_by_id(company_id)
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        
        # Get existing metadata
        extra_metadata = company.extra_metadata or {}
        doc_metadata = extra_metadata.get("documents", {})
        
        # Update document metadata
        doc_metadata[document_type] = {
            "name": name or file.filename or "Document",
            "type": doc_type,
            "size": size_str,
            "uploaded_at": datetime.utcnow().isoformat(),
            "uploaded_by": f"{current_user.first_name} {current_user.last_name}".strip() if current_user else "System",
        }
        extra_metadata["documents"] = doc_metadata
        
        # Update company with new document URL
        field_name = DOCUMENT_TYPE_MAPPING[document_type]
        
        # Build update kwargs based on document type
        update_kwargs = {
            "company_id": company_id,
            "extra_metadata": extra_metadata,
        }
        update_kwargs[field_name] = doc_url
        
        updated_company = await service.update_company(**update_kwargs)
        
        if not updated_company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        
        return DocumentResponse(
            document_type=document_type,
            name=doc_metadata[document_type]["name"],
            url=doc_url,
            type=doc_type,
            size=size_str,
            uploaded_at=doc_metadata[document_type]["uploaded_at"],
            uploaded_by=doc_metadata[document_type]["uploaded_by"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.put("/documents/{document_type}", response_model=DocumentResponse, responses=RESPONSES)
async def update_document(
    document_type: str,
    company_id: UUID,
    request: UpdateDocumentRequest,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Update document metadata (name).
    
    - **document_type**: Document type ('reference', 'sop', 'csr_sop', 'sales_sop')
    - **company_id**: Company UUID
    
    Required role: EXECUTIVE
    """
    try:
        if document_type not in DOCUMENT_TYPE_MAPPING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type. Must be one of: {list(DOCUMENT_TYPE_MAPPING.keys())}",
            )
        
        service = CompanyService(db)
        company = await service.get_company_by_id(company_id)
        
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        
        # Get document URL for this type
        field_name = DOCUMENT_TYPE_MAPPING[document_type]
        doc_url = getattr(company, field_name, None)
        
        if not doc_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document of type '{document_type}' not found",
            )
        
        # Update metadata
        extra_metadata = company.extra_metadata or {}
        doc_metadata = extra_metadata.get("documents", {})
        
        if document_type not in doc_metadata:
            doc_metadata[document_type] = {}
        
        if request.name:
            doc_metadata[document_type]["name"] = request.name
        
        extra_metadata["documents"] = doc_metadata
        
        await service.update_company(
            company_id=company_id,
            extra_metadata=extra_metadata,
        )
        
        # Return updated document
        meta = doc_metadata.get(document_type, {})
        return DocumentResponse(
            document_type=document_type,
            name=meta.get("name", f"{document_type.replace('_', ' ').title()} Document"),
            url=doc_url,
            type=meta.get("type", "PDF"),
            size=meta.get("size"),
            uploaded_at=meta.get("uploaded_at"),
            uploaded_by=meta.get("uploaded_by"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/documents/{document_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_type: str,
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - current_user: User = Depends(require_executive),
    current_user: User = Depends(require_executive),  # RBAC DISABLED - Returns dummy user
):
    """
    Delete a document.
    
    - **document_type**: Document type ('reference', 'sop', 'csr_sop', 'sales_sop')
    - **company_id**: Company UUID
    
    Required role: EXECUTIVE
    """
    try:
        if document_type not in DOCUMENT_TYPE_MAPPING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid document type. Must be one of: {list(DOCUMENT_TYPE_MAPPING.keys())}",
            )
        
        service = CompanyService(db)
        company = await service.get_company_by_id(company_id)
        
        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Company not found",
            )
        
        # Get document URL for this type
        field_name = DOCUMENT_TYPE_MAPPING[document_type]
        doc_url = getattr(company, field_name, None)
        
        if not doc_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document of type '{document_type}' not found",
            )
        
        # Update company to remove document URL
        update_data = {field_name: None}
        
        # Also remove from metadata
        extra_metadata = company.extra_metadata or {}
        doc_metadata = extra_metadata.get("documents", {})
        if document_type in doc_metadata:
            del doc_metadata[document_type]
        extra_metadata["documents"] = doc_metadata
        update_data["extra_metadata"] = extra_metadata
        
        await service.update_company(
            company_id=company_id,
            **update_data,
        )
        
        # Note: We don't delete from S3 here, but could add that if needed
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
