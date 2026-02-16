"""
SOP Processing Background Tasks

Background tasks for processing SOP documents.
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.config import get_settings
from app.core.redis_client import get_redis_client
from app.core.database import get_database
from app.core.milvus_client import get_milvus_client, get_milvus_collection
from app.models.enums import ProcessingStatus, SOPStatus, SOPType, CorpusType
from app.services.sop.document_service import DocumentService
from app.services.sop.extraction_service import ExtractionService
from app.services.sop.validation_service import ValidationService
from app.services.sop.chunking_service import ChunkingService
from app.services.sop.metric_extraction_service import MetricExtractionService
from app.services.call_processing.embedding_service import get_embedding_service

settings = get_settings()
logger = logging.getLogger(__name__)


async def update_sop_job_status(
    job_id: str,
    status: ProcessingStatus,
    progress_percent: int = 0,
    current_step: str = "",
    error: Dict[str, Any] = None,
    sop_id: str = None,
    results: Dict[str, Any] = None
):
    """Update SOP processing job status in Redis"""
    try:
        redis = await get_redis_client()
        cache_key = f"sop_job:{job_id}:status"
        
        # Get existing data
        existing_data = {}
        try:
            existing = await redis.get(cache_key)
            if existing:
                existing_data = json.loads(existing)
        except:
            pass
        
        status_data = {
            "job_id": job_id,
            "sop_id": sop_id or existing_data.get("sop_id", ""),
            "status": status.value,
            "progress": {
                "percent": progress_percent,
                "current_step": current_step
            },
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Set started_at if this is the first update
        if status == ProcessingStatus.PROCESSING and not existing_data.get("started_at"):
            status_data["started_at"] = datetime.utcnow().isoformat()
        elif existing_data.get("started_at"):
            status_data["started_at"] = existing_data["started_at"]
        
        # Set completed_at if status is completed
        if status == ProcessingStatus.COMPLETED:
            status_data["completed_at"] = datetime.utcnow().isoformat()
            if results:
                status_data["results"] = results
        
        if error:
            status_data["error"] = error
            status_data["failed_at"] = datetime.utcnow().isoformat()
        
        await redis.setex(
            cache_key,
            86400,  # 24 hour TTL
            json.dumps(status_data)
        )
    except Exception as e:
        logger.error(f"Failed to update SOP job status: {e}")


async def process_sop_document_background(
    job_id: str,
    sop_id: str,
    file_bytes: bytes,
    filename: str,
    file_type: str,
    company_id: str,
    sop_name: str,
    target_role: Optional[str] = None,
    webhook_url: Optional[str] = None,
    is_new_version: bool = False,
    activation_date: Optional[datetime] = None,
    created_by: Optional[str] = None
):
    """
    Background task for processing SOP document through the pipeline.
    
    Steps:
    1. Extract text from PDF/Word
    2. Validate as SOP
    3. Chunk document
    4. Extract metrics (rolling)
    5. Store in MongoDB
    6. Index in Milvus
    7. Activate SOP
    8. Send webhook notification
    """
    try:
        logger.info(f"Starting SOP processing: {sop_id} (job: {job_id})")
        
        # Initialize services
        db = await get_database()
        doc_service = DocumentService(db)
        extraction_service = ExtractionService()
        validation_service = ValidationService()
        chunking_service = ChunkingService()
        metric_service = MetricExtractionService()
        embedding_service = get_embedding_service()
        get_milvus_client()  # Initialize connection
        milvus_collection = get_milvus_collection()  # Get collection
        
        # Update status: Extracting
        await update_sop_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            progress_percent=15,
            current_step="extracting",
            sop_id=sop_id
        )
        
        # STEP 1: Extract text
        logger.info(f"Extracting text from {filename}")
        extracted_content = await extraction_service.extract_from_bytes(
            file_bytes,
            file_type,
            filename
        )
        
        # Update file info with counts
        page_count = len(extracted_content.sections) if extracted_content.sections else 0
        word_count = len(extracted_content.raw_text.split()) if extracted_content.raw_text else 0
        
        await doc_service.update_sop_document(sop_id, {
            "extracted_content": extracted_content.model_dump(),
            "file_info.page_count": page_count,
            "file_info.word_count": word_count
        })
        
        # Update status: Validating
        await update_sop_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            progress_percent=25,
            current_step="validating",
            sop_id=sop_id
        )
        
        # STEP 2: Validate as SOP
        logger.info(f"Validating SOP document {sop_id}")
        document_preview = extracted_content.raw_text[:5000]
        validation_result = await validation_service.validate_sop_document(
            document_preview,
            filename
        )
        
        if not validation_result.get("is_sop"):
            # Not a valid SOP
            error_detail = {
                "code": "INVALID_SOP_DOCUMENT",
                "message": "Please upload a valid SOP document",
                "details": {
                    "rejection_reason": validation_result.get("rejection_reason"),
                    "confidence": validation_result.get("confidence"),
                    "suggestions": [
                        "Ensure document contains procedural guidelines",
                        "Include role-specific instructions",
                        "Add measurable performance metrics"
                    ]
                }
            }
            
            await doc_service.update_sop_status(sop_id, SOPStatus.FAILED)
            await update_sop_job_status(
                job_id,
                ProcessingStatus.FAILED,
                progress_percent=25,
                current_step="validation_failed",
                error=error_detail,
                sop_id=sop_id
            )
            return
        
        # Update SOP type based on validation
        sop_type = validation_result.get("sop_type", "general_sop")
        await doc_service.update_sop_document(sop_id, {
            "sop_type": sop_type
        })
        
        # Update status: Chunking
        await update_sop_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            progress_percent=35,
            current_step="chunking",
            sop_id=sop_id
        )
        
        # STEP 3: Chunk document
        logger.info(f"Chunking SOP document {sop_id}")
        chunks = await chunking_service.chunk_document(
            extracted_content,
            sop_id,
            company_id
        )
        
        # Save chunks to database
        await doc_service.save_chunks(chunks)
        
        # Update status: Extracting metrics
        await update_sop_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            progress_percent=55,
            current_step="extracting_metrics",
            sop_id=sop_id
        )
        
        # STEP 4: Extract metrics (rolling)
        logger.info(f"Extracting metrics from {len(chunks)} chunks")
        metrics = await metric_service.extract_metrics_rolling(chunks, sop_id)
        
        # Normalize metrics
        metrics = await metric_service.normalize_metrics(metrics)
        
        # Validate metrics
        metrics_validation = await validation_service.validate_extracted_metrics(
            [m.model_dump() for m in metrics]
        )
        
        if not metrics_validation.get("valid"):
            logger.warning(f"Metrics validation warnings: {metrics_validation.get('warnings')}")
        
        # Update status: Validating metrics
        await update_sop_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            progress_percent=70,
            current_step="validating_metrics",
            sop_id=sop_id
        )
        
        # STEP 5: Store metrics in MongoDB
        logger.info(f"Saving {len(metrics)} metrics")
        await doc_service.save_metrics(
            sop_id,
            company_id,
            [m.model_dump() for m in metrics],
            target_role,
            target_role is None
        )
        
        # Update status: Indexing
        await update_sop_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            progress_percent=90,
            current_step="indexing",
            sop_id=sop_id
        )
        
        # STEP 6: Index in Milvus
        logger.info(f"Indexing {len(chunks)} chunks in Milvus")
        vectors_indexed = 0
        
        for chunk in chunks:
            try:
                # Generate embedding
                embedding = await embedding_service.generate_embedding(chunk.text)
                
                # Prepare data for Milvus (with all required schema fields)
                data = {
                    "id": f"sop_{sop_id}_{chunk.chunk_id}",
                    "tenant_id": company_id,
                    "company_id": company_id,  # Required by schema
                    "corpus_type": CorpusType.SOP_DOCUMENT.value,
                    "doc_id": sop_id,
                    "chunk_id": chunk.chunk_id,
                    "text_content": chunk.text[:65000],  # Milvus VARCHAR limit
                    "summary_json": json.dumps({
                        "section": chunk.section_title,
                        "chunk_type": chunk.chunk_type.value if hasattr(chunk.chunk_type, 'value') else str(chunk.chunk_type)
                    }),
                    "created_at": int(datetime.utcnow().timestamp()),
                    "embedding": embedding,
                    "customer_phone": "",  # Not applicable for SOPs
                    "call_date": "",  # Not applicable for SOPs
                    "sentiment": 0.0,  # Not applicable for SOPs
                    "qualification_status": "",  # Not applicable for SOPs
                    "booking_status": "",  # Not applicable for SOPs
                }
                
                # Insert to Milvus collection
                milvus_collection.insert([data])
                
                # Update chunk with milvus_id
                await db.sop_chunks.update_one(
                    {"chunk_id": chunk.chunk_id},
                    {"$set": {"milvus_id": data["id"]}}
                )
                
                vectors_indexed += 1
                
            except Exception as e:
                logger.error(f"Failed to index chunk {chunk.chunk_id}: {e}")
        
        # Index metrics as well
        for metric in metrics:
            try:
                # Handle both dict and Pydantic model types
                if hasattr(metric, 'model_dump'):
                    # It's a Pydantic model
                    metric_dict = metric.model_dump()
                    metric_id = metric.metric_id
                    metric_name = metric.metric_name
                    description = metric.description
                    eval_method = metric.evaluation_method
                    target = metric.target_value
                    weight = metric.weight
                    roles = metric.applicable_roles
                    eval_criteria = metric.evaluation_criteria.model_dump() if hasattr(metric.evaluation_criteria, 'model_dump') else (metric.evaluation_criteria or {})
                else:
                    # It's already a dict
                    metric_dict = metric
                    metric_id = metric.get('metric_id')
                    metric_name = metric.get('metric_name', '')
                    description = metric.get('description', '')
                    eval_method = metric.get('evaluation_method', '')
                    target = metric.get('target_value', 1.0)
                    weight = metric.get('weight', 0.0)
                    roles = metric.get('applicable_roles', [])
                    eval_criteria = metric.get('evaluation_criteria', {})
                
                # Create rich searchable text from metric
                metric_text = f"""{metric_name}

Description: {description}

Evaluation Method: {eval_method}

Target: {target}
Weight: {weight * 100}%

Evaluation Criteria:
- Excellent: {eval_criteria.get('excellent', '')}
- Good: {eval_criteria.get('good', '')}
- Needs Improvement: {eval_criteria.get('needs_improvement', '')}
- Poor: {eval_criteria.get('poor', '')}

Applicable Roles: {', '.join(roles)}
"""
                
                embedding = await embedding_service.generate_embedding(metric_text)
                
                data = {
                    "id": f"sop_metric_{sop_id}_{metric_id}",
                    "tenant_id": company_id,
                    "company_id": company_id,  # Required by schema
                    "corpus_type": CorpusType.SOP_METRIC.value,
                    "doc_id": sop_id,
                    "chunk_id": metric_id,
                    "text_content": metric_text[:65000],
                    "summary_json": json.dumps(metric_dict),
                    "created_at": int(datetime.utcnow().timestamp()),
                    "embedding": embedding,
                    "customer_phone": "",  # Not applicable for metrics
                    "call_date": "",  # Not applicable for metrics
                    "sentiment": 0.0,  # Not applicable for metrics
                    "qualification_status": "",  # Not applicable for metrics
                    "booking_status": "",  # Not applicable for metrics
                }
                
                milvus_collection.insert([data])
                vectors_indexed += 1
                
            except Exception as e:
                logger.error(f"Failed to index metric {metric_id if 'metric_id' in locals() else 'unknown'}: {e}", exc_info=True)
        
        # Flush collection to ensure all vectors are persisted
        milvus_collection.flush()
        logger.info(f"Indexed {vectors_indexed} vectors to Milvus")
        
        # STEP 7: Handle versioning
        from app.services.sop.version_service import get_version_service
        version_service = get_version_service(db)
        
        if is_new_version:
            # Create new version and archive the old one
            version_info = await version_service.create_new_version(
                company_id=company_id,
                sop_id=sop_id,
                file_bytes=file_bytes,
                filename=filename,
                metrics=metrics,
                sop_name=sop_name,
                activation_date=activation_date,
                created_by=created_by
            )
            
            new_version = version_info["version"]
            history_id = version_info["history_id"]
            
            # Update SOP document with version info
            await doc_service.update_sop_document(sop_id, {
                "version": new_version,
                "version_history_id": history_id,
                "activation_date": activation_date or datetime.utcnow()
            })
            
            logger.info(f"Created new version {new_version} for SOP {sop_id}")
        else:
            # INITIAL SOP (version 1) - also create version history record!
            import hashlib
            file_hash = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"
            
            history_id = f"sop_hist_{uuid.uuid4().hex[:12]}"
            new_version = 1
            
            # Create version 1 history record so it can be archived later
            from app.models.sop import SOPVersionHistory
            history_record = SOPVersionHistory(
                history_id=history_id,
                sop_id=sop_id,
                company_id=company_id,
                version=1,
                sop_name=sop_name,
                created_at=datetime.utcnow(),
                created_by=created_by,
                activation_date=datetime.utcnow(),
                archived_at=None,
                status="active",
                metrics_snapshot=[m.model_dump() if hasattr(m, 'model_dump') else m for m in metrics],
                total_metrics=len(metrics),
                total_weight=sum(m.weight if hasattr(m, 'weight') else m.get('weight', 0.1) for m in metrics),
                file_hash=file_hash,
                original_filename=filename
            )
            
            await db.sop_version_history.insert_one(history_record.model_dump(by_alias=True))
            
            # Update SOP document with version info
            await doc_service.update_sop_document(sop_id, {
                "version": 1,
                "version_history_id": history_id,
                "activation_date": datetime.utcnow()
            })
            
            logger.info(f"Created initial version 1 for SOP {sop_id} (history_id: {history_id})")
        
        # STEP 8: Activate SOP (unless scheduled)
        if not activation_date or activation_date <= datetime.utcnow():
            await doc_service.update_sop_status(sop_id, SOPStatus.ACTIVE)
        else:
            logger.info(f"SOP {sop_id} scheduled for activation at {activation_date}")
        
        # Update processing metadata
        await doc_service.update_sop_document(sop_id, {
            "processing_metadata": {
                "job_id": job_id,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "chunks_created": len(chunks),
                "vectors_indexed": vectors_indexed,
                "version": new_version if is_new_version else 1
            }
        })
        
        # Update status: Completed
        results = {
            "sop_id": sop_id,
            "sop_name": sop_name,
            "sop_type": sop_type,
            "is_company_wide": target_role is None,
            "target_role": target_role,
            "metrics_extracted": len(metrics),
            "chunks_indexed": vectors_indexed,
            "page_count": page_count,
            "word_count": word_count
        }
        
        await update_sop_job_status(
            job_id,
            ProcessingStatus.COMPLETED,
            progress_percent=100,
            current_step="completed",
            sop_id=sop_id,
            results=results
        )
        
        logger.info(f"SOP processing completed: {sop_id}")
        
        # Send webhook notification if URL provided
        if webhook_url:
            from app.utils.webhook import send_webhook_notification
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=job_id,
                status="completed",
                event_type="sop_processing",
                payload_data={
                    "sop_id": sop_id,
                    "sop_name": sop_name,
                    "sop_type": sop_type,
                    "company_id": company_id,
                    "target_role": target_role,
                    "is_company_wide": target_role is None,
                    "results": {
                        "metrics_extracted": len(metrics),
                        "chunks_indexed": vectors_indexed,
                        "page_count": page_count,
                        "word_count": word_count
                    },
                    "document_url": f"/api/v1/sop/documents/{sop_id}",
                    "metrics_url": f"/api/v1/sop/metrics/{company_id}?sop_id={sop_id}"
                }
            )
        
    except Exception as e:
        logger.error(f"SOP processing failed for {sop_id}: {str(e)}", exc_info=True)
        
        # Update status: Failed
        error_detail = {
            "code": "PROCESSING_ERROR",
            "message": f"Failed to process SOP document: {str(e)}",
            "details": {"error_type": type(e).__name__}
        }
        
        await doc_service.update_sop_status(sop_id, SOPStatus.FAILED)
        await update_sop_job_status(
            job_id,
            ProcessingStatus.FAILED,
            error=error_detail,
            sop_id=sop_id
        )
        
        # Send webhook notification for failure if URL provided
        if webhook_url:
            from app.utils.webhook import send_webhook_notification
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=job_id,
                status="failed",
                event_type="sop_processing",
                payload_data={
                    "sop_id": sop_id,
                    "company_id": company_id,
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__,
                        "code": error_detail["code"]
                    }
                }
            )


async def process_reanalysis_background(job_id: str):
    """
    Background task for processing SOP re-analysis job.
    
    Called when user triggers manual re-analysis (per Q5-Q8).
    """
    try:
        logger.info(f"Starting re-analysis job: {job_id}")
        
        db = await get_database()
        from app.services.sop.reanalysis_service import get_reanalysis_service
        reanalysis_service = get_reanalysis_service(db)
        
        # Process the reanalysis job
        result = await reanalysis_service.process_reanalysis_job(job_id)
        
        logger.info(f"Re-analysis job completed: {job_id} - {result}")
        
    except Exception as e:
        logger.error(f"Re-analysis job failed: {job_id}: {str(e)}", exc_info=True)
        
        # Update job status to failed
        try:
            db = await get_database()
            await db.reanalysis_jobs.update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.utcnow(),
                        "error": str(e)
                    }
                }
            )
        except Exception as update_error:
            logger.error(f"Failed to update job status: {update_error}")


async def check_scheduled_activations():
    """
    Background task to check and activate scheduled SOP versions (per Q4).
    
    Should be run every minute by a scheduler.
    Finds versions where:
    - status = "scheduled"
    - activation_date <= now
    
    Then activates them by:
    1. Archiving current active version
    2. Activating the scheduled version
    3. Clearing relevant caches
    """
    try:
        db = await get_database()
        from app.services.sop.version_service import get_version_service
        version_service = get_version_service(db)
        
        now = datetime.utcnow()
        
        # Find scheduled versions ready for activation
        cursor = db.sop_version_history.find({
            "status": "scheduled",
            "activation_date": {"$lte": now}
        })
        
        scheduled_versions = await cursor.to_list(length=100)
        
        if not scheduled_versions:
            return
        
        logger.info(f"Found {len(scheduled_versions)} scheduled versions to activate")
        
        for version in scheduled_versions:
            try:
                history_id = version["history_id"]
                sop_id = version["sop_id"]
                
                # Activate the version
                success = await version_service.activate_scheduled_version(history_id)
                
                if success:
                    logger.info(f"Activated scheduled version {history_id} for SOP {sop_id}")
                    
                    # Clear Redis cache for this SOP
                    try:
                        redis = await get_redis_client()
                        await redis.delete(f"sop:{sop_id}:metrics")
                        await redis.delete(f"sop:{sop_id}:active_version")
                    except Exception as cache_error:
                        logger.warning(f"Failed to clear cache for SOP {sop_id}: {cache_error}")
                else:
                    logger.warning(f"Failed to activate scheduled version {history_id}")
                    
            except Exception as e:
                logger.error(f"Error activating version {version.get('history_id')}: {e}")
                continue
        
    except Exception as e:
        logger.error(f"Scheduled activation check failed: {e}", exc_info=True)

