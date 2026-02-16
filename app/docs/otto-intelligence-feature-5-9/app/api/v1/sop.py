"""
SOP Document Ingestion API Endpoints
"""

import logging
from typing import Optional, List, Dict
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Path, Body
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.database import get_database
from app.core.redis_client import get_redis_client
from app.models.enums import ProcessingStatus, SOPStatus
from app.schemas.sop import (
    SOPUploadResponse,
    SOPStatusResponse,
    SOPProgressInfo,
    SOPProcessingResults,
    SOPMetricsResponse,
    CompanySOPMetricsResponse,
    SOPDocumentResponse,
    SOPListResponse,
    SOPListItem,
    SOPStatusUpdateRequest,
    SOPStatusUpdateResponse,
    MetricResponse
)
from app.services.sop.document_service import DocumentService
from app.services.sop.document_download_service import get_document_download_service
from app.services.sop.version_service import get_version_service
from app.services.sop.reanalysis_service import get_reanalysis_service
from app.tasks.sop_tasks import process_sop_document_background, process_reanalysis_background
from app.utils.uuid_validator import validate_uuid
import json
import uuid

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sop", tags=["SOP Document Ingestion"])


@router.post("/documents/upload", response_model=SOPUploadResponse, status_code=202)
async def upload_sop_document(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
    company_id: str = Form(...),
    sop_name: str = Form(...),
    target_role: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    webhook_url: Optional[str] = Form(None)
):
    """
    Upload SOP document for processing.
    
    Supports two methods:
    1. Direct file upload: Provide 'file' parameter with actual file (use -F 'file=@/path/to/file.pdf')
    2. URL download: Provide 'file_url' parameter with URL string (use -F 'file_url=s3://bucket/key' or -F 'file_url=https://...')
    
    Exactly one of 'file' or 'file_url' must be provided.
    
    Supported URL formats for file_url:
    - S3: s3://bucket/path/to/document.pdf
    - HTTP/HTTPS: https://example.com/document.pdf
    - Local: file:///path/to/document.pdf or /absolute/path/document.pdf
    
    Accepted formats: PDF, DOC, DOCX
    Returns job_id for status tracking.
    """
    try:
        # Validate company_id is UUID
        try:
            validate_uuid(company_id, "company_id")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Validate that exactly one of file or file_url is provided
        if not file and not file_url:
            raise HTTPException(
                status_code=400,
                detail="Either 'file' (for file upload) or 'file_url' (for URL download) must be provided"
            )
        
        if file and file_url:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'file' OR 'file_url', not both"
            )
        
        # Get file bytes based on method
        if file_url:
            # Download from URL (S3, HTTP, or local path)
            logger.info(f"Downloading document from URL: {file_url}")
            document_download_service = get_document_download_service()
            
            try:
                file_bytes, content_type, filename = await document_download_service.download_document(
                    file_url,
                    max_size_mb=50
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to download document from URL: {str(e)}"
                )
        else:
            # Direct file upload
            if not file.content_type:
                raise HTTPException(status_code=400, detail="File content type is required")
            
            content_type = file.content_type
            filename = file.filename
            
            # Read file
            file_bytes = await file.read()
        
        # Validate file size
        file_size = len(file_bytes)
        max_size = 50 * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size} bytes. Maximum: {max_size} bytes (50MB)"
            )
        
        # Validate file type
        allowed_types = [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
        
        if content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}. Allowed: PDF, DOC, DOCX"
            )
        
        # Parse metadata
        metadata_dict = {}
        if metadata:
            try:
                metadata_dict = json.loads(metadata)
            except:
                raise HTTPException(status_code=400, detail="Invalid metadata JSON")
        
        # Create SOP document entry
        db = await get_database()
        doc_service = DocumentService(db)
        
        sop_id = await doc_service.create_sop_document(
            company_id=company_id,
            sop_name=sop_name,
            file_bytes=file_bytes,
            filename=filename,
            file_type=content_type,
            target_role=target_role,
            metadata=metadata_dict
        )
        
        # Generate job ID as pure UUID
        job_id = str(uuid.uuid4())
        
        # Initialize job status in Redis
        redis = await get_redis_client()
        status_data = {
            "job_id": job_id,
            "sop_id": sop_id,
            "status": ProcessingStatus.QUEUED.value,
            "progress": {
                "percent": 0,
                "current_step": "queued"
            },
            "created_at": datetime.utcnow().isoformat()
        }
        
        await redis.setex(
            f"sop_job:{job_id}:status",
            86400,  # 24 hour TTL
            json.dumps(status_data)
        )
        
        # Schedule background processing
        background_tasks.add_task(
            process_sop_document_background,
            job_id=job_id,
            sop_id=sop_id,
            file_bytes=file_bytes,
            filename=filename,
            file_type=content_type,
            company_id=company_id,
            sop_name=sop_name,
            target_role=target_role,
            webhook_url=webhook_url
        )
        
        source = "URL" if file_url else "file upload"
        logger.info(f"SOP upload initiated from {source}: {sop_id} (job: {job_id})")
        
        return SOPUploadResponse(
            job_id=job_id,
            status=ProcessingStatus.QUEUED,
            message=f"SOP document processing initiated from {source}",
            file_name=filename,
            file_size=file_size,
            status_url=f"/api/v1/sop/documents/status/{job_id}",
            created_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/documents/status/{job_id}", response_model=SOPStatusResponse)
async def get_sop_processing_status(job_id: str):
    """
    Get SOP processing status.
    
    Poll this endpoint to check progress.
    """
    # Validate job_id is UUID
    try:
        validate_uuid(job_id, "job_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        redis = await get_redis_client()
        cache_key = f"sop_job:{job_id}:status"
        
        status_data = await redis.get(cache_key)
        
        if not status_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        data = json.loads(status_data)
        
        # Build progress info
        progress = data.get("progress", {})
        progress_info = SOPProgressInfo(
            percent=progress.get("percent", 0),
            current_step=progress.get("current_step", ""),
            steps_completed=progress.get("steps_completed", []),
            steps_remaining=progress.get("steps_remaining", [])
        )
        
        # Build response
        response = SOPStatusResponse(
            job_id=job_id,
            status=ProcessingStatus(data.get("status", "queued")),
            progress=progress_info,
            started_at=data.get("started_at"),
            updated_at=data.get("updated_at"),
            completed_at=data.get("completed_at"),
            failed_at=data.get("failed_at"),
            duration_seconds=None,
            results=None,
            error=data.get("error")
        )
        
        # Add results if completed
        if data.get("status") == "completed" and data.get("results"):
            results_data = data["results"]
            response.results = SOPProcessingResults(**results_data)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.get("/metrics/{company_id}", response_model=CompanySOPMetricsResponse)
async def get_company_sop_metrics(
    company_id: str = Path(..., description="Company ID (UUID format)"),
    role: Optional[str] = None,
    sop_id: Optional[str] = None
):
    """
    Get active SOP metrics for a company.
    
    Returns role-specific and company-wide SOPs.
    """
    try:
        # Validate company_id is UUID
        try:
            validate_uuid(company_id, "company_id")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # sop_id can be any string format, no validation needed
        
        db = await get_database()
        doc_service = DocumentService(db)
        
        # Get metrics
        if sop_id:
            # Get specific SOP metrics
            metrics_doc = await db.sop_metrics.find_one({"sop_id": sop_id})
            if not metrics_doc:
                raise HTTPException(status_code=404, detail="SOP not found")
            
            sop_doc = await doc_service.get_sop_document(sop_id)
            
            metrics_response = _build_metrics_response(metrics_doc, sop_doc)
            
            return CompanySOPMetricsResponse(
                company_id=company_id,
                active_sops=[metrics_response],
                company_wide_sops=[]
            )
        
        # Get all active SOPs for company
        query = {
            "company_id": company_id,
            "status": SOPStatus.ACTIVE.value
        }
        
        if role:
            # Get role-specific SOPs
            query["target_role"] = role
        
        cursor = db.sop_metrics.find(query)
        metrics_docs = await cursor.to_list(length=100)
        
        # Separate role-specific and company-wide
        role_specific = []
        company_wide = []
        
        for metrics_doc in metrics_docs:
            sop_doc = await doc_service.get_sop_document(metrics_doc["sop_id"])
            metrics_response = _build_metrics_response(metrics_doc, sop_doc)
            
            if metrics_doc.get("is_company_wide"):
                company_wide.append(metrics_response)
            else:
                role_specific.append(metrics_response)
        
        return CompanySOPMetricsResponse(
            company_id=company_id,
            active_sops=role_specific,
            company_wide_sops=company_wide
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get metrics error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/documents/{sop_id}", response_model=SOPDocumentResponse)
async def get_sop_document(sop_id: str = Path(..., description="SOP ID (string or UUID)")):
    """
    Get SOP document details.
    """
    try:
        # sop_id can be any string format, no validation needed
        
        db = await get_database()
        doc_service = DocumentService(db)
        
        sop_doc = await doc_service.get_sop_document(sop_id)
        
        if not sop_doc:
            raise HTTPException(status_code=404, detail="SOP document not found")
        
        # Get metrics for summary
        metrics_doc = await db.sop_metrics.find_one({"sop_id": sop_id})
        
        metrics_summary = {}
        if metrics_doc:
            metrics = metrics_doc.get("metrics", [])
            categories = {}
            for metric in metrics:
                cat = metric.get("category", "general")
                categories[cat] = categories.get(cat, 0) + 1
            
            metrics_summary = {
                "total_metrics": len(metrics),
                "by_category": categories
            }
        
        # Extract sections info
        sections = []
        extracted_content = sop_doc.get("extracted_content", {})
        for section in extracted_content.get("sections", []):
            sections.append({
                "title": section.get("title"),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end")
            })
        
        return SOPDocumentResponse(
            sop_id=sop_doc["sop_id"],
            company_id=sop_doc["company_id"],
            sop_name=sop_doc["sop_name"],
            sop_type=sop_doc["sop_type"],
            target_role=sop_doc.get("target_role"),
            is_company_wide=sop_doc.get("is_company_wide", False),
            file_info=sop_doc.get("file_info", {}),
            sections=sections,
            metrics_summary=metrics_summary,
            status=SOPStatus(sop_doc["status"]),
            version=sop_doc.get("version"),
            created_at=sop_doc["created_at"],
            updated_at=sop_doc["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get document error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")


@router.patch("/documents/{sop_id}/status", response_model=SOPStatusUpdateResponse)
async def update_sop_status(
    sop_id: str = Path(..., description="SOP ID (string or UUID)"),
    request: SOPStatusUpdateRequest = ...
):
    """
    Update SOP document status (activate/deactivate).
    """
    try:
        # sop_id can be any string format, no validation needed
        
        db = await get_database()
        doc_service = DocumentService(db)
        
        sop_doc = await doc_service.get_sop_document(sop_id)
        
        if not sop_doc:
            raise HTTPException(status_code=404, detail="SOP document not found")
        
        previous_status = SOPStatus(sop_doc["status"])
        
        # Update status
        await doc_service.update_sop_status(sop_id, request.status, request.reason)
        
        return SOPStatusUpdateResponse(
            sop_id=sop_id,
            previous_status=previous_status,
            new_status=request.status,
            updated_at=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update status error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")


@router.get("/documents", response_model=SOPListResponse)
async def list_sop_documents(
    company_id: str,
    status: Optional[str] = None,
    target_role: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    """
    List SOP documents for a company.
    """
    try:
        # Validate company_id is UUID
        try:
            validate_uuid(company_id, "company_id")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        db = await get_database()
        doc_service = DocumentService(db)
        
        result = await doc_service.list_sops(
            company_id=company_id,
            status=status,
            target_role=target_role,
            page=page,
            limit=limit
        )
        
        # Convert documents to list items
        list_items = []
        for doc in result["documents"]:
            # Get metrics count
            metrics_doc = await db.sop_metrics.find_one({"sop_id": doc["sop_id"]})
            metrics_count = len(metrics_doc.get("metrics", [])) if metrics_doc else 0
            
            list_items.append(SOPListItem(
                sop_id=doc["sop_id"],
                sop_name=doc["sop_name"],
                sop_type=doc["sop_type"],
                target_role=doc.get("target_role"),
                is_company_wide=doc.get("is_company_wide", False),
                status=SOPStatus(doc["status"]),
                version=doc.get("version"),
                metrics_count=metrics_count,
                created_at=doc["created_at"]
            ))
        
        return SOPListResponse(
            company_id=company_id,
            total=result["total"],
            page=page,
            limit=limit,
            documents=list_items
        )
        
    except Exception as e:
        logger.error(f"List documents error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.delete("/documents/{sop_id}", status_code=204)
async def delete_sop_document(sop_id: str = Path(..., description="SOP ID (string or UUID)")):
    """
    Delete SOP document and all associated data.
    """
    try:
        # sop_id can be any string format, no validation needed
        
        db = await get_database()
        doc_service = DocumentService(db)
        
        sop_doc = await doc_service.get_sop_document(sop_id)
        
        if not sop_doc:
            raise HTTPException(status_code=404, detail="SOP document not found")
        
        # Delete document and related data
        await doc_service.delete_sop(sop_id)
        
        # TODO: Also delete from Milvus
        
        return JSONResponse(status_code=204, content=None)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


def _build_metrics_response(metrics_doc: dict, sop_doc: Optional[dict]) -> SOPMetricsResponse:
    """Helper to build metrics response"""
    metrics = []
    for m in metrics_doc.get("metrics", []):
        metrics.append(MetricResponse(**m))
    
    return SOPMetricsResponse(
        sop_id=metrics_doc["sop_id"],
        sop_name=sop_doc.get("sop_name", "") if sop_doc else "",
        sop_type=sop_doc.get("sop_type", "general_sop") if sop_doc else "general_sop",
        target_role=metrics_doc.get("target_role"),
        is_company_wide=metrics_doc.get("is_company_wide", False),
        version=sop_doc.get("version") if sop_doc else None,
        total_metrics=metrics_doc.get("total_metrics", 0),
        metrics=metrics,
        created_at=metrics_doc.get("created_at", datetime.utcnow()),
        status=SOPStatus(metrics_doc.get("status", "active"))
    )


# ============================================================================
# SOP VERSION CONTROL ENDPOINTS (per Q1-Q9)
# ============================================================================

from pydantic import BaseModel, Field
from typing import List as TypeList


class SOPVersionResponse(BaseModel):
    """Response for a single SOP version"""
    history_id: str
    sop_id: str
    version: int
    sop_name: str
    status: str
    created_at: datetime
    created_by: Optional[str] = None
    activation_date: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    total_metrics: int
    file_hash: str
    original_filename: str


class SOPVersionHistoryResponse(BaseModel):
    """Response for version history"""
    sop_id: str
    current_version: int
    total_versions: int
    versions: TypeList[SOPVersionResponse]


class ReanalysisJobResponse(BaseModel):
    """Response for reanalysis job"""
    job_id: str
    sop_id: str
    new_sop_version: int
    lookback_days: int
    status: str
    total_calls: int
    message: str
    status_url: str


class ResultsSummary(BaseModel):
    """Summary of reanalysis results"""
    calls_improved: int
    calls_declined: int
    calls_unchanged: int
    avg_score_change: float  # Percentage change
    avg_old_score: float
    avg_new_score: float


class MetricChange(BaseModel):
    """Change info for a single metric"""
    metric_id: str
    avg_change: float  # Percentage change
    direction: str  # "improved", "declined", "stable"
    avg_old_score: float
    avg_new_score: float


class ReanalysisResultsResponse(BaseModel):
    """Response for reanalysis results"""
    job_id: str
    sop_id: str
    status: str
    total_calls: int
    processed_calls: int
    failed_calls: int
    skipped_calls: int = 0  # Calls already evaluated with current SOP version
    skipped_reason: Optional[str] = None  # Reason for skipping (e.g., "already_evaluated_with_current_version")
    calls_improved: int
    calls_declined: int
    calls_unchanged: int
    avg_score_change: Optional[float] = None
    avg_old_score: Optional[float] = None
    avg_new_score: Optional[float] = None
    results_summary: Optional[ResultsSummary] = None  # Detailed results summary
    metric_changes: Optional[Dict[str, MetricChange]] = None  # Per-metric change analysis
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


@router.post("/documents/{sop_id}/versions", status_code=202)
async def upload_new_version(
    background_tasks: BackgroundTasks,
    sop_id: str = Path(..., description="SOP ID"),
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
    activation_date: Optional[datetime] = Form(None),
    created_by: Optional[str] = Form(None),
    webhook_url: Optional[str] = Form(None)
):
    """
    Upload new version of existing SOP (per Q1-Q4).
    
    - Automatically archives current version (Q2)
    - Auto-increments version number (Q1)
    - Supports scheduled activation (Q4)
    
    Supports file upload or URL download.
    """
    try:
        db = await get_database()
        doc_service = DocumentService(db)
        version_service = get_version_service(db)
        
        # Verify SOP exists
        sop_doc = await doc_service.get_sop_document(sop_id)
        if not sop_doc:
            raise HTTPException(status_code=404, detail=f"SOP {sop_id} not found")
        
        # Validate file input
        if not file and not file_url:
            raise HTTPException(
                status_code=400,
                detail="Either 'file' or 'file_url' must be provided"
            )
        
        if file and file_url:
            raise HTTPException(
                status_code=400,
                detail="Provide either 'file' OR 'file_url', not both"
            )
        
        # Get file bytes
        if file_url:
            document_download_service = get_document_download_service()
            file_bytes, content_type, filename = await document_download_service.download_document(
                file_url, max_size_mb=50
            )
        else:
            file_bytes = await file.read()
            content_type = file.content_type
            filename = file.filename
        
        # Validate file type
        allowed_types = [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ]
        
        if content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {content_type}"
            )
        
        # Check for duplicate
        import hashlib
        file_hash = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"
        duplicate = await version_service.check_for_duplicate(sop_id, file_hash)
        
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"This exact file was already uploaded as version {duplicate['version']}"
            )
        
        # Generate job ID for processing
        job_id = str(uuid.uuid4())
        
        # Initialize job status in Redis
        redis = await get_redis_client()
        status_data = {
            "job_id": job_id,
            "sop_id": sop_id,
            "operation": "new_version",
            "status": ProcessingStatus.QUEUED.value,
            "progress": {"percent": 0, "current_step": "queued"},
            "created_at": datetime.utcnow().isoformat()
        }
        
        await redis.setex(
            f"sop_job:{job_id}:status",
            86400,
            json.dumps(status_data)
        )
        
        # Schedule background processing
        background_tasks.add_task(
            process_sop_document_background,
            job_id=job_id,
            sop_id=sop_id,
            file_bytes=file_bytes,
            filename=filename,
            file_type=content_type,
            company_id=sop_doc["company_id"],
            sop_name=sop_doc["sop_name"],
            target_role=sop_doc.get("target_role"),
            webhook_url=webhook_url,
            is_new_version=True,
            activation_date=activation_date,
            created_by=created_by
        )
        
        current_version = sop_doc.get("version", 1)
        
        return {
            "job_id": job_id,
            "sop_id": sop_id,
            "current_version": current_version,
            "new_version": current_version + 1,
            "status": "queued",
            "activation_date": activation_date or "immediate",
            "message": f"Version {current_version + 1} upload initiated",
            "status_url": f"/api/v1/sop/documents/status/{job_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Version upload error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/documents/{sop_id}/versions", response_model=SOPVersionHistoryResponse)
async def get_version_history(
    sop_id: str = Path(..., description="SOP ID"),
    include_archived: bool = True
):
    """
    Get all versions of an SOP.
    
    Returns version history sorted by version number descending.
    """
    try:
        db = await get_database()
        version_service = get_version_service(db)
        doc_service = DocumentService(db)
        
        # Verify SOP exists
        sop_doc = await doc_service.get_sop_document(sop_id)
        if not sop_doc:
            raise HTTPException(status_code=404, detail=f"SOP {sop_id} not found")
        
        versions = await version_service.get_version_history(sop_id, include_archived)
        
        version_responses = [
            SOPVersionResponse(
                history_id=v["history_id"],
                sop_id=v["sop_id"],
                version=v["version"],
                sop_name=v["sop_name"],
                status=v["status"],
                created_at=v["created_at"],
                created_by=v.get("created_by"),
                activation_date=v.get("activation_date"),
                archived_at=v.get("archived_at"),
                total_metrics=v.get("total_metrics", 0),
                file_hash=v["file_hash"],
                original_filename=v["original_filename"]
            )
            for v in versions
        ]
        
        return SOPVersionHistoryResponse(
            sop_id=sop_id,
            current_version=sop_doc.get("version", 1),
            total_versions=len(versions),
            versions=version_responses
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get version history error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{sop_id}/versions/{version}")
async def get_specific_version(
    sop_id: str = Path(..., description="SOP ID"),
    version: int = Path(..., description="Version number", ge=1)
):
    """
    Get specific version details including metrics snapshot.
    """
    try:
        db = await get_database()
        version_service = get_version_service(db)
        
        version_doc = await version_service.get_specific_version(sop_id, version)
        
        if not version_doc:
            raise HTTPException(
                status_code=404,
                detail=f"Version {version} not found for SOP {sop_id}"
            )
        
        return version_doc
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get version error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{sop_id}/reanalyze", response_model=ReanalysisJobResponse)
async def trigger_reanalysis(
    background_tasks: BackgroundTasks,
    sop_id: str = Path(..., description="SOP ID"),
    lookback_days: int = 14,
    company_id: str = Form(...)
):
    """
    Trigger manual re-analysis of calls with current SOP version (per Q5-Q7).
    
    - Re-analyzes ALL calls in lookback period (Q7)
    - Default lookback: 14 days (Q6)
    - Stores both original and new evaluations (Q8)
    """
    try:
        # Validate company_id
        try:
            validate_uuid(company_id, "company_id")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        db = await get_database()
        reanalysis_service = get_reanalysis_service(db)
        
        # Create reanalysis job
        job_id = await reanalysis_service.trigger_reanalysis(
            sop_id=sop_id,
            company_id=company_id,
            lookback_days=lookback_days
        )
        
        # Get job info
        job_doc = await db.reanalysis_jobs.find_one({"job_id": job_id})
        
        # Schedule background processing
        background_tasks.add_task(
            process_reanalysis_background,
            job_id=job_id
        )
        
        return ReanalysisJobResponse(
            job_id=job_id,
            sop_id=sop_id,
            new_sop_version=job_doc["new_sop_version"],
            lookback_days=lookback_days,
            status="queued",
            total_calls=job_doc["total_calls"],
            message=f"Re-analysis initiated for {job_doc['total_calls']} calls",
            status_url=f"/api/v1/sop/reanalysis/{job_id}"
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trigger reanalysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reanalysis/{job_id}", response_model=ReanalysisResultsResponse)
async def get_reanalysis_results(
    job_id: str = Path(..., description="Reanalysis job ID")
):
    """
    Get re-analysis job status and results.
    """
    try:
        validate_uuid(job_id, "job_id")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    try:
        db = await get_database()
        reanalysis_service = get_reanalysis_service(db)
        
        results = await reanalysis_service.get_reanalysis_results(job_id)
        
        # Build results_summary if available
        results_summary = None
        if results.get("results_summary"):
            rs = results["results_summary"]
            results_summary = ResultsSummary(
                calls_improved=rs.get("calls_improved", 0),
                calls_declined=rs.get("calls_declined", 0),
                calls_unchanged=rs.get("calls_unchanged", 0),
                avg_score_change=rs.get("avg_score_change", 0),
                avg_old_score=rs.get("avg_old_score", 0),
                avg_new_score=rs.get("avg_new_score", 0)
            )
        
        # Build metric_changes if available
        metric_changes = None
        if results.get("metric_changes"):
            metric_changes = {}
            for metric_name, mc in results["metric_changes"].items():
                metric_changes[metric_name] = MetricChange(
                    metric_id=mc.get("metric_id", ""),
                    avg_change=mc.get("avg_change", 0),
                    direction=mc.get("direction", "stable"),
                    avg_old_score=mc.get("avg_old_score", 0),
                    avg_new_score=mc.get("avg_new_score", 0)
                )
        
        return ReanalysisResultsResponse(
            job_id=results["job_id"],
            sop_id=results["sop_id"],
            status=results["status"],
            total_calls=results["total_calls"],
            processed_calls=results.get("processed_calls", 0),
            failed_calls=results.get("failed_calls", 0),
            skipped_calls=results.get("skipped_calls", 0),
            skipped_reason=results.get("skipped_reason"),
            calls_improved=results.get("calls_improved", 0),
            calls_declined=results.get("calls_declined", 0),
            calls_unchanged=results.get("calls_unchanged", 0),
            avg_score_change=results.get("avg_score_change"),
            avg_old_score=results.get("avg_old_score"),
            avg_new_score=results.get("avg_new_score"),
            results_summary=results_summary,
            metric_changes=metric_changes,
            created_at=results["created_at"],
            completed_at=results.get("completed_at"),
            error=results.get("error")
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Get reanalysis results error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

