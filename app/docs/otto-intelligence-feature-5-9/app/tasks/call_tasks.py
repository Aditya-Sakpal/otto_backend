"""
Call Processing Background Tasks (No Celery)

Background tasks for processing calls using FastAPI BackgroundTasks.

Enhanced with:
- Tenant configuration
- Call type detection for existing customers
- Role detection
- Home services context
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any

from ..config import get_settings
from ..core.redis_client import get_redis_client
from ..core.database import get_database
from ..core.background_tasks import BackgroundTaskManager
from ..services.call_processing.audio_service import get_audio_service
from ..services.call_processing.transcription_service import get_transcription_service
from ..services.call_processing.chunking_service import get_chunking_service
from ..services.call_processing.summary_service import get_summary_service
from ..services.call_processing.rag_service import get_rag_service
from ..services.call_processing.customer_history_service import get_customer_history_service
# Note: role_detector removed from pipeline - trust provided rep_role instead
# from ..services.call_processing.role_detector import get_role_detector
from ..services.tenant_config_service import TenantConfigService
from ..models.enums import ProcessingStatus, compute_call_outcome_category, QualificationStatus, BookingStatus

settings = get_settings()
logger = logging.getLogger(__name__)


async def update_job_status(
    job_id: str,
    status: ProcessingStatus,
    progress_percent: int = 0,
    current_step: str = "",
    error: Dict[str, Any] = None,
    call_id: str = None
):
    """Update job status in Redis"""
    try:
        redis = await get_redis_client()
        cache_key = f"job:{job_id}:status"
        
        # Get existing data to preserve call_id
        existing_data = {}
        try:
            existing = await redis.get(cache_key)
            if existing:
                existing_data = json.loads(existing)
        except:
            pass
        
        status_data = {
            "job_id": job_id,
            "call_id": call_id or existing_data.get("call_id", ""),  # Preserve or update call_id
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
        
        if error:
            status_data["error"] = error
        
        await redis.setex(
            cache_key,
            86400,  # 24 hour TTL
            json.dumps(status_data)
        )
    except Exception as e:
        logger.error(f"Failed to update job status: {e}")


async def process_call_background(job_id: str, request_data: Dict[str, Any]):
    """
    Background task for processing a call through the entire pipeline.
    
    This runs in the FastAPI process, not a separate worker.
    
    Enhanced Pipeline:
    1. Download audio
    2. Transcribe with diarization
    3. Get tenant configuration
    4. Get customer history and detect call type
    5. Detect rep role
    6. Chunk transcript
    7. Generate summary (with all context)
    8. Apply tenant rules
    9. Index in RAG
    10. Store in MongoDB
    """
    call_id = request_data["call_id"]
    company_id = request_data["company_id"]
    audio_url = request_data["audio_url"]
    phone_number = request_data["phone_number"]
    
    # Get webhook URL and convert to string if it's a Pydantic URL object
    webhook_url = request_data.get("webhook_url")
    if webhook_url:
        webhook_url = str(webhook_url)  # Convert Pydantic Url to string
    
    try:
        logger.info(f"Starting call processing: {call_id} (job: {job_id})")
        
        # Update status: Processing
        await update_job_status(
            job_id,
            ProcessingStatus.PROCESSING,
            5,
            "initializing",
            call_id=call_id
        )
        
        # Step 0: Get tenant configuration
        db = await get_database()
        tenant_config_service = TenantConfigService(db)
        tenant_config = await tenant_config_service.get_config(company_id)
        logger.info(f"Loaded tenant config for {company_id} (version: {tenant_config.version})")
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 10, "downloading_audio", call_id=call_id)
        
        # Step 1: Download audio
        audio_service = get_audio_service()
        audio_path = await audio_service.download_audio(audio_url)
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 20, "transcribing")
        
        # Step 2: Transcribe with diarization and speaker labeling
        transcription_service = get_transcription_service()
        
        # Build initial call context for transcription
        from datetime import datetime as dt
        call_date_value = request_data.get("call_date")
        if call_date_value:
            if isinstance(call_date_value, str):
                try:
                    call_date_dt = dt.fromisoformat(call_date_value.replace('Z', '+00:00'))
                except:
                    call_date_dt = dt.utcnow()
            else:
                call_date_dt = call_date_value
        else:
            call_date_dt = dt.utcnow()
        
        initial_call_context = {
            "call_id": call_id,
            "company_id": company_id,
            "phone_number": phone_number,
            "call_date": call_date_dt.strftime("%Y-%m-%d"),
            "rep_role": request_data.get("rep_role", "customer_rep")
        }
        
        transcript_data = await transcription_service.transcribe(
            audio_path,
            call_context=initial_call_context
        )
        transcript_text = transcript_data["transcript"]
        segments = transcript_data.get("segments", [])
        segments_with_timestamps = transcript_data.get("segments_with_timestamps", [])
        
        # Log segment information
        logger.info(
            f"Transcription complete: {len(segments)} segments (speaker-labeled), "
            f"{len(segments_with_timestamps)} timestamped segments"
        )
        
        # Cleanup audio file
        audio_service.cleanup_temp_file(audio_path)
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 40, "chunking")
        
        # Step 3: Chunk transcript with semantic/speaker-aware chunking
        chunking_service = get_chunking_service()
        chunks = chunking_service.chunk_transcript(
            transcript_text,
            call_id,
            segments=segments  # Use labeled segments for semantic chunking
        )
        
        logger.info(f"Created {len(chunks)} chunks using {chunks[0].get('chunking_method', 'unknown')} method")
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 45, "getting_customer_context")
        
        # Step 3.5: Get customer history and detect call type
        # Note: is_existing_customer is now extracted by LLM from transcript (not DB check)
        customer_history_service = get_customer_history_service()
        customer_context = await customer_history_service.get_full_customer_context(
            phone_number=phone_number,
            company_id=company_id,
            transcript=transcript_text
        )
        
        call_type_result = customer_context.get("call_type_detection") or {}
        # is_existing_customer will be determined by LLM from transcript (in qualification extraction)
        # We keep customer_history for call type detection and context enrichment
        
        # Get rep_role from request (no need to detect - trust the caller)
        rep_role = request_data.get("rep_role", "customer_rep")
        logger.info(f"Using provided rep_role: {rep_role}")
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 50, "summarizing")
        
        # Step 4: Generate summary with call context and customer history
        summary_service = get_summary_service()
        
        # Build comprehensive call context for intelligent extraction
        call_context = {
            "call_id": call_id,
            "company_id": company_id,
            "phone_number": phone_number,
            "call_date": call_date_dt.strftime("%Y-%m-%d"),
            "call_time": call_date_dt.strftime("%H:%M:%S"),
            "timezone": request_data.get("timezone", "UTC"),
            "company_services": request_data.get("company_services", []),
            "company_service_area": request_data.get("company_service_area", ""),
            "rep_role": rep_role,
            "diarization_available": len(segments) > 0,
            "diarization_method": transcript_data.get("diarization_method", "unknown"),
            # Customer context (for call type detection and history enrichment)
            # Note: is_existing_customer is now extracted by LLM from transcript
            "call_type_detection": call_type_result,
            "customer_history": customer_context.get("customer_history"),
            # Tenant configuration
            "tenant_config": tenant_config,
        }
        
        summary, chunk_summaries_with_llm = await summary_service.generate_summary(
            chunks, 
            call_id, 
            company_id,
            rep_role=rep_role,
            call_context=call_context
        )
        
        # Step 4.5: Post-processing with tenant rules and call type
        summary = apply_post_processing(
            summary, 
            call_context, 
            tenant_config_service, 
            tenant_config,
            customer_history_service,
            call_type_result
        )
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 70, "indexing_rag")
        
        # Step 5: Index in RAG (if not skipped)
        if not request_data.get("options", {}).get("skip_rag_indexing", False):
            rag_service = get_rag_service()
            
            # Index call summary
            # Convert call_date to string for Milvus (expects VARCHAR)
            call_date_value = request_data.get("call_date")
            if call_date_value:
                if isinstance(call_date_value, str):
                    call_date_str = call_date_value
                else:
                    # It's a datetime object
                    call_date_str = call_date_value.isoformat()
            else:
                call_date_str = ""
            
            milvus_id = await rag_service.index_call_summary(
                call_id=call_id,
                company_id=company_id,
                summary_text=summary["summary"]["summary"],
                summary_json=summary,
                customer_phone=phone_number,
                call_date=call_date_str,
                metadata={
                    "sentiment": summary["summary"].get("sentiment_score", 0.5),
                    "qualification_status": summary["qualification"].get("qualification_status", ""),
                    "booking_status": summary["qualification"].get("booking_status", "")
                }
            )
            
            # Index chunk summaries with actual LLM-generated content
            for chunk in chunks:
                # Get the corresponding LLM-generated summary
                chunk_llm_summary = None
                for cs in chunk_summaries_with_llm:
                    if cs["chunk_id"] == chunk["chunk_id"]:
                        chunk_llm_summary = cs["summary"]
                        break
                
                # Use LLM summary if available, otherwise create basic summary
                if chunk_llm_summary:
                    # Extract summary text from the nested structure
                    if isinstance(chunk_llm_summary, dict) and "summary" in chunk_llm_summary:
                        summary_text = chunk_llm_summary["summary"].get("summary", chunk["text"][:1000])
                    else:
                        summary_text = chunk["text"][:1000]
                else:
                    summary_text = chunk["text"][:1000]
                    chunk_llm_summary = {
                        "summary": f"Chunk {chunk['chunk_index']} of call",
                        "key_points": [],
                        "sentiment_score": 0.5
                    }
                
                await rag_service.index_chunk_summary(
                    chunk_id=chunk["chunk_id"],
                    call_id=call_id,
                    company_id=company_id,
                    summary_text=summary_text,
                    summary_json=chunk_llm_summary,  # Now using actual LLM summary!
                    chunk_index=chunk["chunk_index"],  # Add missing parameter
                    metadata={
                        "customer_phone": phone_number,
                        "call_date": call_date_str,  # Use converted string
                        "sentiment": chunk_llm_summary.get("sentiment_score", 0.5) if isinstance(chunk_llm_summary, dict) else 0.5
                    }
                )
        
        await update_job_status(job_id, ProcessingStatus.PROCESSING, 90, "storing_database")
        
        # Step 6: Store in MongoDB (following ARCHITECTURE_FEATURE_1_CALL_PIPELINE.md)
        db = await get_database()
        
        # 6.1 Store in `calls` collection - basic call data
        call_document = {
            "call_id": call_id,
            "company_id": company_id,
            "customer_id": None,  # Could be linked later
            "phone_number": phone_number,
            "audio_url": audio_url,
            "duration": request_data.get("duration"),
            "call_date": request_data.get("call_date"),
            "status": ProcessingStatus.COMPLETED.value,
            "transcript": transcript_text,
            "segments": segments,  # Store speaker-labeled segments (for display and context)
            "segments_with_timestamps": segments_with_timestamps,  # Store original timestamped segments (for phase detection)
            "diarization_metadata": {
                "method": transcript_data.get("diarization_method", "unknown"),
                "speaker_labeling": transcript_data.get("speaker_labeling_method", "unknown"),
                "segment_count": len(segments),
                "timestamped_segment_count": len(segments_with_timestamps)
            },
            "created_at": datetime.utcnow(),
            "processed_at": datetime.utcnow(),
            "metadata": request_data.get("metadata", {})
        }
        
        await db.calls.update_one(
            {"call_id": call_id},
            {"$set": call_document},
            upsert=True
        )
        
        # 6.2 Store in `call_summaries` collection - structured summary
        call_summary_document = {
            "call_id": call_id,
            "company_id": company_id,
            "summary": summary.get("summary", {}),
            "compliance": summary.get("compliance", {}),
            "objections": summary.get("objections", {}),
            "qualification": summary.get("qualification", {}),
            "lead_score": summary.get("lead_score", {}),
            "sop_evaluation": summary.get("sop_evaluation", {}),  # SOP compliance with version tracking
            "milvus_id": f"vec_{call_id}_summary",
            "created_at": datetime.utcnow()
        }
        
        await db.call_summaries.update_one(
            {"call_id": call_id},
            {"$set": call_summary_document},
            upsert=True
        )
        
        # 6.3 Store in `chunk_summaries` collection - individual chunks with LLM summaries
        for i, chunk in enumerate(chunks):
            # Get the corresponding LLM-generated summary
            chunk_llm_summary = None
            for cs in chunk_summaries_with_llm:
                if cs["chunk_id"] == chunk["chunk_id"]:
                    chunk_llm_summary = cs["summary"]
                    break
            
            # Fallback to basic info if LLM summary not found
            if not chunk_llm_summary:
                chunk_llm_summary = {
                    "summary": f"Chunk {chunk['chunk_index']} of call",
                    "key_points": [],
                    "sentiment_score": 0.5
                }
            
            chunk_summary_document = {
                "chunk_id": chunk["chunk_id"],
                "call_id": call_id,
                "company_id": company_id,
                "chunk_index": chunk["chunk_index"],
                "text": chunk["text"],
                "summary": chunk_llm_summary,  # Now using actual LLM-generated summary!
                "milvus_id": f"vec_{call_id}_chunk_{chunk['chunk_index']}",
                "created_at": datetime.utcnow()
            }
            
            await db.chunk_summaries.update_one(
                {"chunk_id": chunk["chunk_id"]},
                {"$set": chunk_summary_document},
                upsert=True
            )
        
        logger.info(f"Stored call data across 3 collections: calls, call_summaries, chunk_summaries")
        
        # =====================================================================
        # STEP 7: Conversation Phase Detection (per Q49-Q60)
        # Enhanced in v1.1: Uses diarized segments for accurate timestamps
        # =====================================================================
        try:
            logger.info(f"Detecting conversation phases for call {call_id}")
            from ..services.call_processing.phase_detection_service import get_phase_detection_service
            
            phase_service = get_phase_detection_service()
            
            # Get call duration - prefer from duration field, then metadata, then segments
            call_duration_ms = None
            if request_data.get("duration"):
                call_duration_ms = request_data.get("duration") * 1000  # Convert seconds to ms
            elif request_data.get("metadata", {}).get("duration_ms"):
                call_duration_ms = request_data.get("metadata", {}).get("duration_ms")
            elif segments_with_timestamps and len(segments_with_timestamps) > 0:
                # Calculate from last segment end time
                last_segment = segments_with_timestamps[-1]
                call_duration_ms = int(last_segment.get("end_time", 0) * 1000)
            
            # Use timestamped segments if available, otherwise fall back to labeled segments
            # For hybrid alignment, pass both LLM segments (accurate speakers) and API segments (accurate timestamps)
            has_both_segment_types = segments and len(segments) > 0 and segments_with_timestamps and len(segments_with_timestamps) > 0
            
            if has_both_segment_types:
                logger.info(
                    f"Phase detection using hybrid alignment: "
                    f"{len(segments)} LLM segments + {len(segments_with_timestamps)} API segments"
                )
            else:
                logger.info(f"Phase detection using fallback (single segment type available)")
            
            # Detect phases with hybrid alignment or fallback
            call_phases = await phase_service.detect_phases(
                transcript=transcript_text,
                call_id=call_id,
                company_id=company_id,
                call_duration_ms=call_duration_ms,
                segments=None,  # Legacy parameter - not used when llm_segments and api_segments provided
                llm_segments=segments if segments and len(segments) > 0 else None,  # Accurate speakers
                api_segments=segments_with_timestamps if segments_with_timestamps and len(segments_with_timestamps) > 0 else None  # Accurate timestamps
            )
            
            # Store phase results
            # Use model_dump() without mode='json' to keep datetime as datetime objects
            # This allows MongoDB date queries to work properly
            phases_doc = call_phases.model_dump()
            await db.call_phases.update_one(
                {"call_id": call_id},
                {"$set": phases_doc},
                upsert=True
            )
            
            # Log detection results with timestamp method info
            # Get estimation method from first detected phase
            estimation_method = "word_count"
            for phase_result in call_phases.phases.values():
                if phase_result.detected and phase_result.timestamps:
                    estimation_method = phase_result.timestamps.estimation_method
                    break
            
            logger.info(
                f"Phase detection complete: {call_phases.analytics.phases_detected}/6 phases detected "
                f"(estimation_method: {estimation_method}, algorithm: v{call_phases.algorithm_version})"
            )
            
            if call_phases.has_missing_phases:
                logger.info(f"Missing phases: {call_phases.missing_phases}")
                
        except Exception as e:
            # Phase detection is non-critical - log but don't fail the pipeline
            logger.warning(f"Phase detection failed (non-critical): {e}")
        
        # Update final status
        await update_job_status(
            job_id,
            ProcessingStatus.COMPLETED,
            100,
            "completed",
            call_id=call_id
        )
        
        logger.info(f"Call processing completed: {call_id} (job: {job_id})")
        
        # Send webhook notification if URL provided
        if webhook_url:
            from ..utils.webhook import send_webhook_notification
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=job_id,
                status="completed",
                event_type="call_processing",
                payload_data={
                    "call_id": call_id,
                    "summary_url": f"/api/v1/call-processing/summary/{call_id}",
                    "chunks_url": f"/api/v1/call-processing/chunks/{call_id}"
                }
            )
        
        return {
            "call_id": call_id,
            "job_id": job_id,
            "status": "completed",
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Call processing failed: {call_id} (job: {job_id}): {str(e)}")
        
        # Update error status
        await update_job_status(
            job_id,
            ProcessingStatus.FAILED,
            0,
            "failed",
            error={
                "code": type(e).__name__.upper(),
                "message": str(e),
                "type": type(e).__name__,
                "details": {},
                "timestamp": datetime.utcnow().isoformat()
            },
            call_id=call_id
        )
        
        # Send webhook notification for failure if URL provided
        if webhook_url:
            from ..utils.webhook import send_webhook_notification
            await send_webhook_notification(
                webhook_url=webhook_url,
                job_id=job_id,
                status="failed",
                event_type="call_processing",
                payload_data={
                    "call_id": call_id,
                    "error": {
                        "message": str(e),
                        "type": type(e).__name__
                    }
                }
            )
        
        raise


def apply_post_processing(
    summary: Dict[str, Any],
    call_context: Dict[str, Any],
    tenant_config_service: TenantConfigService,
    tenant_config,
    customer_history_service,
    call_type_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Apply post-processing to summary results:
    1. Apply tenant-specific qualification rules
    2. Merge with customer history (existing customer handling)
    3. Compute final call outcome category
    
    Args:
        summary: Extracted summary from summary service
        call_context: Call context including customer history
        tenant_config_service: Tenant config service instance
        tenant_config: Loaded tenant configuration
        customer_history_service: Customer history service
        call_type_result: Call type detection result
        
    Returns:
        Post-processed summary
    """
    qualification = summary.get("qualification", {})
    
    # Step 1: Apply tenant-specific qualification rules
    if tenant_config and qualification:
        qualification = tenant_config_service.apply_qualification_rules(qualification, tenant_config)
        summary["qualification"] = qualification
        
        # Check if service is deprioritized
        if qualification.get("is_deprioritized"):
            logger.info(f"Service deprioritized per tenant config: wait time = {qualification.get('service_wait_time_weeks')} weeks")
    
    # Step 2: Merge with customer history if existing customer
    customer_history = call_context.get("customer_history")
    if customer_history and call_type_result:
        qualification = customer_history_service.merge_with_known_customer(
            qualification,
            customer_history,
            call_type_result
        )
        summary["qualification"] = qualification
    
    # Step 3: Compute final call outcome category
    call_type = (call_type_result.get("call_type") or "fresh_sales") if call_type_result else "fresh_sales"
    logger.debug(f"[POST-PROCESSING] call_type={call_type}, type={type(call_type)}")
    
    prev_booking = None
    if customer_history and customer_history.get("last_interaction"):
        prev_booking = customer_history["last_interaction"].get("booking_status")
    logger.debug(f"[POST-PROCESSING] prev_booking={prev_booking}, type={type(prev_booking)}")
    
    is_deprioritized = qualification.get("is_deprioritized", False)
    
    # Map string status to enum
    qual_status_str = qualification.get("qualification_status") or "unqualified"
    logger.debug(f"[POST-PROCESSING] qual_status_str={qual_status_str}, type={type(qual_status_str)}")
    
    try:
        qual_status = QualificationStatus(qual_status_str)
    except ValueError:
        logger.warning(f"[POST-PROCESSING] Invalid qualification_status: {qual_status_str}, using UNQUALIFIED")
        qual_status = QualificationStatus.UNQUALIFIED
    
    booking_status_str = qualification.get("booking_status") or "not_booked"
    logger.debug(f"[POST-PROCESSING] booking_status_str={booking_status_str}, type={type(booking_status_str)}")
    
    try:
        booking_status = BookingStatus(booking_status_str)
    except ValueError:
        logger.warning(f"[POST-PROCESSING] Invalid booking_status: {booking_status_str}, using NOT_BOOKED")
        booking_status = BookingStatus.NOT_BOOKED
    
    # Compute outcome with all context
    logger.debug(f"[POST-PROCESSING] About to call compute_call_outcome_category with: qual_status={qual_status}, booking_status={booking_status}, call_type={call_type}, prev_booking={prev_booking}, is_deprioritized={is_deprioritized}")
    
    final_outcome = compute_call_outcome_category(
        qualification_status=qual_status,
        booking_status=booking_status,
        call_type=call_type,
        previous_booking_status=prev_booking,
        is_deprioritized=is_deprioritized
    )
    
    logger.debug(f"[POST-PROCESSING] compute_call_outcome_category returned: {final_outcome}")
    
    qualification["call_outcome_category"] = final_outcome.value
    
    # Add call type to qualification object (per API documentation)
    qualification["detected_call_type"] = call_type
    
    # Preserve is_existing_customer from LLM extraction (already in qualification from intelligence extraction)
    # If not present (legacy), default to False
    if "is_existing_customer" not in qualification:
        qualification["is_existing_customer"] = False
        logger.info("is_existing_customer not found in qualification, defaulting to False")
    
    # Ensure customer_phone is set from request if not extracted from transcript
    if not qualification.get("customer_phone") and call_context.get("phone_number"):
        qualification["customer_phone"] = call_context.get("phone_number")
        logger.info(f"Set customer_phone from request parameter: {qualification['customer_phone']}")
    
    summary["qualification"] = qualification
    
    # Add metadata about post-processing
    summary["_post_processing"] = {
        "tenant_rules_applied": len(qualification.get("applied_rules", [])),
        "call_type_detected": call_type,
        "is_existing_customer": qualification.get("is_existing_customer", False),
        "final_outcome": final_outcome.value
    }
    
    logger.info(f"Post-processing complete: outcome={final_outcome.value}, call_type={call_type}")
    
    return summary

