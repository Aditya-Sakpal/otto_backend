"""
Leads API routes.

Provides lead management endpoints.
"""
import traceback
from datetime import datetime
from typing import List, Optional, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.dependencies import DbSession
from app.core.permissions import require_manager_or_csr, require_manager_or_sales_rep
from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.models.lead_detail import LeadDetail, PipelineLeadDetail
from app.domain.models.customer_card import CustomerCard
from app.domain.users.models import User
from app.services.lead_service import LeadService
from app.infrastructure.repositories.lead import normalize_lead_list_sort
from pydantic import BaseModel, Field

router = APIRouter()
logger = get_logger(__name__)

RESPONSES = {
    400: {"description": "Bad request (e.g. invalid date format)"},
    403: {"description": "Forbidden"},
    404: {"description": "Lead not found"},
    422: {"description": "Validation error"},
    500: {"description": "Internal server error"},
}

# Example payload shown in Swagger for GET /api/v1/leads/{lead_id}/details
LEAD_DETAIL_EXAMPLE = {
    "id": "bc175381-b349-4cfc-ac23-8085d567665e",
    "created_at": "2026-03-02T09:46:30.204322Z",
    "updated_at": "2026-03-02T22:14:22.586681Z",
    "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
    "status": "closed_won",
    "deal_status": "nurturing",
    "pipeline_stage": "appointment",
    "deal_size": None,
    "contact": {
        "id": "4013a406-29d0-4eb8-aad8-2139735b4254",
        "created_at": "2026-03-23T17:38:15.532212",
        "updated_at": None,
        "first_name": "BRENDA",
        "last_name": "JOHNSON",
        "primary_phone": "6233417153",
        "email": None,
    },
    "agent": {
        "id": "573c5f36-dcc5-4440-b8fd-58699807544a",
        "created_at": "2026-03-23T17:38:15.781301",
        "updated_at": None,
        "first_name": "Diva",
        "last_name": "Shahpur",
        "email": "diva@arizonaroofers.com",
    },
    "overall_engagement": {
        "id": "05752e45-fa3d-40aa-9bf8-3064913778e4",
        "created_at": "2026-03-23T17:38:16.905634",
        "updated_at": None,
        "summary": "Call summary unavailable Call summary unavailable",
        "key_points": [],
        "action_items": [],
        "appointment_status": None,
    },
    "conversations": [
        {
            "id": "5a91dbeb-8818-4ace-998a-b37194f3b6c6",
            "created_at": "2026-03-02T09:46:51.782191Z",
            "updated_at": None,
            "call_type": None,
            "lead_source": None,
            "phone_number": "6233417153",
            "duration_seconds": 54,
            "missed_call": False,
            # Transcript is truncated for readability in Swagger.
            "transcript": "SPEAKER_00: Hi, this is Nika from Arizona Roofers... (truncated)",
            "call_recording_url": "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/4013a406-29d0-4eb8-aad8-2139735b4254/4028711981.mp3",
            "handled_by_user_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
            "summary": "Call summary unavailable",
            "key_points": [],
            "objections": [],
            "sentiment_score": 0.5,
            "sop_compliance_score": 0.5,
            "qualification_status": "cold",
            "booking_status": "not_booked",
            "phases": {
                "greeting": {
                    "phase": "greeting",
                    "detected": True,
                    "confidence": 0.5,
                    "timestamps": {
                        "start_ms": 1920,
                        "end_ms": 4197,
                        "duration_ms": 2277,
                        "estimation_method": "hybrid_aligned",
                    },
                    "segments": [
                        {
                            "start_word_index": 0,
                            "end_word_index": 48,
                            "speaker": "SPEAKER_00",
                            "text": "SPEAKER_00: Hi, this is Nika from Arizona Roofers. How can I",
                        }
                    ],
                    "key_phrases": ["can", "this is"],
                    "quality_score": 0.7,
                    "quality_notes": None,
                },
                "problem_discovery": {
                    "phase": "problem_discovery",
                    "detected": False,
                    "confidence": 0,
                    "timestamps": None,
                    "segments": [],
                    "key_phrases": [],
                    "quality_score": None,
                    "quality_notes": None,
                },
                "qualification": {
                    "phase": "qualification",
                    "detected": False,
                    "confidence": 0,
                    "timestamps": None,
                    "segments": [],
                    "key_phrases": [],
                    "quality_score": None,
                    "quality_notes": None,
                },
                "objection_handling": {
                    "phase": "objection_handling",
                    "detected": False,
                    "confidence": 0,
                    "timestamps": None,
                    "segments": [],
                    "key_phrases": [],
                    "quality_score": None,
                    "quality_notes": None,
                },
                "closing": {
                    "phase": "closing",
                    "detected": True,
                    "confidence": 0.25,
                    "timestamps": {
                        "start_ms": 4151,
                        "end_ms": 7433,
                        "duration_ms": 3282,
                        "estimation_method": "hybrid_aligned",
                    },
                    "segments": [
                        {
                            "start_word_index": 48,
                            "end_word_index": 112,
                            "speaker": "SPEAKER_00",
                            "text": "as per tracking, you are already scheduled for February 19th, 10:00am to 12:00pm okay. I'm sorry. I thought you guys were different companies. That's okay. Not a problem. Thank you very much, Brenda. Be safe. Bye. Bye. You have",
                        }
                    ],
                    "key_phrases": ["schedule", "schedule"],
                    "quality_score": 0.7,
                    "quality_notes": None,
                },
                "post_close": {
                    "phase": "post_close",
                    "detected": False,
                    "confidence": 0,
                    "timestamps": None,
                    "segments": [],
                    "key_phrases": [],
                    "quality_score": None,
                    "quality_notes": None,
                },
            },
        },
        {
            "id": "450b7ac3-b00c-4dc4-9ada-9c7a80e0696f",
            "created_at": "2026-03-02T09:46:35.867614Z",
            "updated_at": None,
            "call_type": None,
            "lead_source": None,
            "phone_number": "6233417153",
            "duration_seconds": 310,
            "missed_call": False,
            "transcript": "SPEAKER_00: Arizona roof. Yes, I was doing. If I can have somebody come out and give me an estimate of a new roof. What's going on? I'm sorry, honey, what? What? What's going on? I just wanted someone to come out and give me a quote on a new roof. Okay. How old is your current roof? 25 years. Okay, and are you the property owner? Yes. Okay, one moment please. Alrighty. Grab your property address. In a sec. Okay. 76 34. What? Oh, sorry, what? No, go ahead. 7634. 7634 west robin lane. Rotman lane. Like r o t r o b I n. Robin lane. Okay. In peoria? Yes. Okay, And then your first last name please? Brenda Johnson. Brenda, do you have a good email I can put on file? Yes. Vernie V E R N I E2222cogs.net and the best phone number to reach you. 623-341-7153. Perfect. Am I able to send you email and text message updates about the roof? I'm sorry, what? Honey? Am I able to send you email and text message updates about the roof? Like appointment confirmation? Okay. Yeah. So you want to reroof the full new roof? Yes. What type of roofing material do you have? Tile, shingle or flat? Tile. Do you know how much square footage the home is? 2136. Do you have any solar panels on the roof? No. Is this a one story hall? Yes. Okay. Is this a gated community? Any gate codes we should be aware of? No. No. Is there an HOA for the neighborhood? Yes. Perfect. And are you the only property owner, Brenda? Yes, we're the only owner. We've been here 25 years. We're the only owners. Perfect. Alrighty. Is there a certain day and time that works best for you to be present during time of inspection? This week. Can you do it on Thursday? This week? Let me check. Yeah, we could do it on Thursday if that works best for you. We have a 10am to 12 slot, if that works. A 10, 10. 10am to 12pm appointment window slot, if that works. Yeah, 10 to 12. Okay, that's fine. Perfect. You'll be getting a text and email confirmation of your appointment and the technician will give you a call when he's on his way, usually 30 minutes before he heads out that way. How it kind of works is Mikhail come out there, chat with you a little bit. You can show him any problem areas since you know what you're looking for. He'll go up there, do a full roof inspection, take about 50 to 100 photos. They'll write up a report and they'll give you multiple quotes. But he'll also give you a full review, quote on whatever you're looking for and kind of discuss everything that we offer with you. Do you have any other questions? No, I don't, honey. Thank you. Of course. You're all set. You will. See you then.",
            "call_recording_url": "https://ottoaudio.s3.ap-southeast-2.amazonaws.com/recordings/4013a406-29d0-4eb8-aad8-2139735b4254/4028701751.mp3",
            "handled_by_user_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
            "summary": "Call summary unavailable",
            "key_points": [],
            "objections": [],
            "sentiment_score": 0.5,
            "sop_compliance_score": 0.5,
            "qualification_status": "cold",
            "booking_status": "not_booked",
            "phases": {
                "greeting": {
                    "phase": "greeting",
                    "detected": False,
                    "confidence": 0,
                    "timestamps": None,
                    "segments": [],
                    "key_phrases": [],
                    "quality_score": None,
                    "quality_notes": None,
                },
                "problem_discovery": {
                    "phase": "problem_discovery",
                    "detected": True,
                    "confidence": 0.25,
                    "timestamps": {
                        "start_ms": 720,
                        "end_ms": 901,
                        "duration_ms": 181,
                        "estimation_method": "hybrid_aligned",
                    },
                    "segments": [
                        {
                            "start_word_index": 0,
                            "end_word_index": 124,
                            "speaker": "SPEAKER_00",
                            "text": "going on? I'm sorry, honey, what? What? What's going on? I just wanted someone to come out and give me a quote on a new roof. Okay. How old is your current roof? 25 years. Okay, and are you the property owner? Yes. Okay, one moment please. Alrighty. Grab your property address. In a sec. Okay. 76 34. What? Oh, sorry, what? No, go ahead. 7634. 7634 west robin lane. Rotman lane. Like r o t r o b I n. Robin lane. Okay. In peoria? Yes. Okay, And then your first last name please? Brenda Johnson. Brenda, do you",
                        }
                    ],
                    "key_phrases": ["going on", "going on"],
                    "quality_score": 0.7,
                    "quality_notes": None,
                },
                "qualification": {
                    "phase": "qualification",
                    "detected": True,
                    "confidence": 0.25,
                    "timestamps": {
                        "start_ms": 899,
                        "end_ms": 1153,
                        "duration_ms": 254,
                        "estimation_method": "hybrid_aligned",
                    },
                    "segments": [
                        {
                            "start_word_index": 124,
                            "end_word_index": 298,
                            "speaker": "SPEAKER_00",
                            "text": "t r o b I n. Robin lane. Okay. In peoria? Yes. Okay, And then your first last name please? Brenda Johnson. Brenda, do you have a good email I can put on file? Yes. Vernie V E R N I E2222cogs.net and the best phone number to reach you. 623-341-7153. Perfect. Am I able to send you email and text message updates about the roof? I'm sorry, what? Honey? Am I able to send you email and text message updates about the roof? Like appointment confirmation? Okay. Yeah. So you want to reroof the full new roof? Yes. What",
                        }
                    ],
                    "key_phrases": [
                        "when he's on his way, usually 30 minutes before he heads out that way. how it kind of works is mikhail come out there, chat with you a little bit. you can show him any problem areas since you know what you're looking for. he'll go up there, do a full roof inspection, take about 50 to 100 photos. they'll write up a report and they'll give you multiple quotes. but he'll also give you a full review, quote on whatever you're looking"
                    ],
                    "quality_score": 0.7,
                    "quality_notes": None,
                },
                "objection_handling": {
                    "phase": "objection_handling",
                    "detected": False,
                    "confidence": 0,
                    "timestamps": None,
                    "segments": [],
                    "key_phrases": [],
                    "quality_score": None,
                    "quality_notes": None,
                },
                "closing": {
                    "phase": "closing",
                    "detected": True,
                    "confidence": 0.25,
                    "timestamps": {
                        "start_ms": 1151,
                        "end_ms": 1370,
                        "duration_ms": 219,
                        "estimation_method": "hybrid_aligned",
                    },
                    "segments": [
                        {
                            "start_word_index": 298,
                            "end_word_index": 448,
                            "speaker": "SPEAKER_00",
                            "text": "for you to be present during time of inspection? This week. Can you do it on Thursday? This week? Let me check. Yeah, we could do it on Thursday if that works best for you. We have a 10am to 12 slot, if that works. A 10, 10. 10am to 12pm appointment window slot, if that works. Yeah, 10 to 12. Okay, that's fine. Perfect. You'll be getting a text and email confirmation of your appointment and the technician will give you a call when he's on his way, usually 30 minutes before he heads out that way. How it",
                        }
                    ],
                    "key_phrases": ["appointment", "appointment"],
                    "quality_score": 0.7,
                    "quality_notes": None,
                },
                "post_close": {
                    "phase": "post_close",
                    "detected": True,
                    "confidence": 0.25,
                    "timestamps": {
                        "start_ms": 1369,
                        "end_ms": 1838,
                        "duration_ms": 469,
                        "estimation_method": "hybrid_aligned",
                    },
                    "segments": [
                        {
                            "start_word_index": 448,
                            "end_word_index": 498,
                            "speaker": "SPEAKER_00",
                            "text": "you're looking for. He'll go up there, do a full roof inspection, take about 50 to 100 photos. They'll write up a report and they'll give you multiple quotes. But he'll also give you a full review, quote on whatever you're looking for and kind of discuss everything that we offer with you. Do you have any other questions? No, I don't, honey. Thank you. Of course. You're all set. You will. See you then.",
                        }
                    ],
                    "key_phrases": ["confirmation", "confirmation"],
                    "quality_score": 0.7,
                    "quality_notes": None,
                },
            },
        },
    ],
}

# Swagger example for GET /leads/{lead_id}/pipeline-detail (includes Shoonya phases per conversation)
_PIPELINE_DETAIL_PHASES_EXAMPLE = {
    "greeting": {
        "phase": "greeting",
        "detected": True,
        "confidence": 0.5,
        "timestamps": {
            "start_ms": 1920,
            "end_ms": 4197,
            "duration_ms": 2277,
            "estimation_method": "hybrid_aligned",
        },
        "segments": [
            {
                "start_word_index": 0,
                "end_word_index": 12,
                "speaker": "SPEAKER_00",
                "text": "Hi, thanks for calling — how can we help?",
            }
        ],
        "key_phrases": ["thanks for calling"],
        "quality_score": 0.7,
        "quality_notes": None,
    },
    "problem_discovery": {
        "phase": "problem_discovery",
        "detected": False,
        "confidence": 0,
        "timestamps": None,
        "segments": [],
        "key_phrases": [],
        "quality_score": None,
        "quality_notes": None,
    },
    "qualification": {
        "phase": "qualification",
        "detected": False,
        "confidence": 0,
        "timestamps": None,
        "segments": [],
        "key_phrases": [],
        "quality_score": None,
        "quality_notes": None,
    },
    "objection_handling": {
        "phase": "objection_handling",
        "detected": False,
        "confidence": 0,
        "timestamps": None,
        "segments": [],
        "key_phrases": [],
        "quality_score": None,
        "quality_notes": None,
    },
    "closing": {
        "phase": "closing",
        "detected": False,
        "confidence": 0,
        "timestamps": None,
        "segments": [],
        "key_phrases": [],
        "quality_score": None,
        "quality_notes": None,
    },
    "post_close": {
        "phase": "post_close",
        "detected": False,
        "confidence": 0,
        "timestamps": None,
        "segments": [],
        "key_phrases": [],
        "quality_score": None,
        "quality_notes": None,
    },
}

PIPELINE_DETAIL_EXAMPLE = {
    "pipeline_stage": "appointment",
    "lead": {
        "id": "bc175381-b349-4cfc-ac23-8085d567665e",
        "status": "qualified_booked",
        "overall_engagement": {
            "last_touched": "2026-03-02T09:46:51.782191Z",
            "next_move": "Send estimate follow-up",
            "summary": "Customer interested in roof estimate.",
            "key_points": ["Scheduled inspection window discussed"],
        },
        "conversations": [
            {
                "id": "5a91dbeb-8818-4ace-998a-b37194f3b6c6",
                "call_type": "csr_call",
                "lead_source": None,
                "duration_seconds": 310,
                "created_at": "2026-03-02T09:46:51.782191Z",
                "booking_status": "not_booked",
                "qualification_status": "warm",
                "summary": "CSR call summary…",
                "key_points": [],
                "objections": [],
                "call_recording_url": "https://example.com/recording.mp3",
                "phases": _PIPELINE_DETAIL_PHASES_EXAMPLE,
            }
        ],
    },
    "appointment": None,
    "result": {
        "outcome": "won",
        "outcome_summary": "Sold full roof replacement.",
        "deal_size": 18500.0,
        "key_lesson": None,
        "overall_engagement": {
            "last_touched": "2026-03-10T14:00:00Z",
            "next_move": None,
            "summary": "On-site appointment closed.",
            "key_points": ["Customer signed"],
        },
        "conversations": [
            {
                "id": "7c2f4a10-1111-4222-8333-444455556666",
                "call_type": None,
                "lead_source": None,
                "duration_seconds": 2400,
                "created_at": "2026-03-10T14:00:00Z",
                "booking_status": "booked",
                "qualification_status": "hot",
                "summary": "Appointment recording summary…",
                "key_points": ["Warranty explained"],
                "objections": [],
                "call_recording_url": "https://example.com/appt-recording.mp3",
                "phases": _PIPELINE_DETAIL_PHASES_EXAMPLE,
            }
        ],
        "follow_up": None,
    },
    "follow_up": None,
}


@router.get("", response_model=List[Lead], responses=RESPONSES)
async def list_leads(
    company_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
    status_filter: Optional[str] = Query(None, alias="status"),
    nurturing: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="Filter leads created on or after this date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter leads created on or before this date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by contact name or phone number"),
    skip: int = 0,
    limit: int = 100,
) -> List[Lead]:
    """
    List leads for a company with optional filters.
    
    Access: EXECUTIVE, CSR
    
    Query Parameters:
    - status: Filter by status (comma-separated for multiple, e.g., "qualified_unbooked" or "closed_lost,abandoned,dormant")
    - nurturing: Filter nurturing leads (comma-separated, e.g., "new,warm,hot")
    - sort: Sort option: `created_desc` (default), `created_asc`, `name_asc`, `name_desc`, `priority`;
      also accepts common aliases (`most_recent`, `oldest_first`, `name_a_z`, `name_z_a`, camelCase).
    - start_date: Filter leads created on or after this date (YYYY-MM-DD)
    - end_date: Filter leads created on or before this date (YYYY-MM-DD)
    - search: Search by contact name or phone number
    """
    try:
        from datetime import date as date_type
        service = LeadService(db)
        start_d = None
        end_d = None
        if start_date:
            try:
                start_d = date_type.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be YYYY-MM-DD")
        if end_date:
            try:
                end_d = date_type.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be YYYY-MM-DD")
        sort_key = normalize_lead_list_sort(sort)
        use_filters = start_d is not None or end_d is not None or (search and search.strip())
        if use_filters:
            statuses = None
            if status_filter:
                statuses = [s.strip() for s in status_filter.split(",")]
                if nurturing:
                    statuses.extend([s.strip() for s in nurturing.split(",")])
                    statuses = list(set(statuses))
            elif nurturing:
                statuses = [s.strip() for s in nurturing.split(",")]
            return await service.list_with_filters(
                company_id=company_id,
                start_date=start_d,
                end_date=end_d,
                search=search.strip() if search else None,
                statuses=statuses,
                skip=skip,
                limit=limit,
                sort=sort_key,
            )
        # Filter by status
        if status_filter:
            statuses = [s.strip() for s in status_filter.split(",")]
            if nurturing:
                nurturing_statuses = [s.strip() for s in nurturing.split(",")]
                statuses.extend(nurturing_statuses)
                statuses = list(set(statuses))
            return await service.get_by_statuses(
                company_id=company_id,
                statuses=statuses,
                skip=skip,
                limit=limit,
                sort=sort_key,
            )
        # Filter by nurturing only
        if nurturing:
            nurturing_statuses = [s.strip() for s in nurturing.split(",")]
            return await service.get_nurturing(
                company_id=company_id,
                statuses=nurturing_statuses,
                skip=skip,
                limit=limit,
                sort=sort_key,
            )
        # Default: return all leads
        return await service.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
            sort=sort_key,
        )
    except Exception as e:
        logger.error(f"Error listing leads: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/pipeline", response_model=Dict[str, List[Lead]], responses=RESPONSES)
async def get_pipeline_view(
    company_id: UUID,
    db: DbSession,
    limit: int = Query(20, ge=1, le=500, description="Max leads per pipeline stage"),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> Dict[str, List[Lead]]:
    """
    Get leads grouped by pipeline stage.

    Returns a dictionary with all pipeline stages as keys
    (qualified, unqualified, service_not_offered, booked, appointment, appointment_ran, won, lost, review),
    each containing an array of leads in that stage (capped by `limit`).

    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        return await service.get_pipeline_view(company_id=company_id, limit=limit)
    except Exception as e:
        logger.error(f"Error getting pipeline view: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{lead_id}", response_model=Lead, responses=RESPONSES)
async def get_lead(
    lead_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> Lead:
    """
    Get lead by ID.
    
    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        lead = await service.get_by_id(lead_id)
        
        if not lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        return lead
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lead: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{lead_id}/details",
    response_model=LeadDetail,
    responses={
        **RESPONSES,
        200: {
            "description": "Lead detail response",
            "content": {"application/json": {"example": LEAD_DETAIL_EXAMPLE}},
        },
    },
)
async def get_lead_details(
    lead_id: UUID,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> LeadDetail:
    """
    Get detailed lead information for lead details page.
    
    Returns comprehensive lead information including:
    - Contact information (name, phone, email)
    - Assigned agent information
    - Overall engagement (summary, key points, action items, appointment status)
    - Conversations array (all calls with this lead, sorted by most recent first)
      Each conversation includes:
      - Call details (type, phone number, duration, transcript, recording URL)
      - Analysis data (summary, key points, objections, sentiment, SOP compliance)
      - Phases data (greeting, problem_discovery, qualification, objection_handling, closing, post_close)
        Each phase includes detection status, confidence, timestamps, segments, key phrases, and quality scores
    
    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        lead_detail = await service.get_detail_by_id(lead_id)
        
        if not lead_detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        return lead_detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lead details: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{lead_id}/pipeline-detail",
    response_model=PipelineLeadDetail,
    responses={
        **RESPONSES,
        200: {
            "description": "Pipeline lead detail (3-tab) with Shoonya conversation phases on each call",
            "content": {
                "application/json": {
                    "example": PIPELINE_DETAIL_EXAMPLE,
                }
            },
        },
    },
)
async def get_pipeline_lead_detail(
    lead_id: UUID,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> PipelineLeadDetail:
    """
    Get 3-tab pipeline lead detail view.

    Returns structured data for the three tabs shown in the pipeline card detail:

    - **lead** (always present): CSR stage — overall engagement (last touched, next move,
      summary, key points) and all conversations (calls) with their analysis data.
      Each item in `lead.conversations` may include **`phases`** (Shoonya call conversation
      phases: greeting, problem_discovery, qualification, etc.) when Shunya is configured.
    - **appointment** (present when a linked appointment exists): appointment details
      including contact name, assigned sales rep, status, location, date/time, meeting URL.
    - **result** (present when appointment has been conducted): outcome engagement
      (last touched, next move, summary, key points) and the appointment interaction call(s).
      Each item in `result.conversations` may include the same **`phases`** shape for that call.

    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        detail = await service.get_pipeline_detail_by_id(lead_id)

        if not detail:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )

        return detail
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pipeline lead detail: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/{lead_id}/customer-card", response_model=CustomerCard, responses=RESPONSES)
async def get_customer_card(
    lead_id: UUID,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> CustomerCard:
    """
    Get the full customer card for a lead.

    Returns comprehensive data for the customer card view including:

    **Header**: contact info (name, phone, initials), pipeline stage progress bar,
    assigned rep, deal size, status pills.

    **Lead tab** (always present):
    - Overall engagement (last touched, next move, summary, key points, action items)
    - Conversations with full analysis (booking status, qualification, SOP checklist,
      compliance scores, sentiment, objections, call recording URL)
    - Coaching tips

    **Appointment tab** (when appointment exists):
    - Appointment details (sales rep, status, outcome, location, schedule)
    - Recording & transcript
    - SOP compliance checklist
    - Comments / posts from team members

    **Result tab** (when appointment has outcome/analysis):
    - Outcome (deal value, key lesson)
    - Follow-up tracking (pending/completed tasks, overdue status, next follow-up)
    - Engagement summary & conversations

    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        card = await service.get_customer_card(lead_id)

        if not card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )

        return card
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting customer card: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


class AssignLeadRequest(BaseModel):
    """Request to assign a lead to a sales rep."""
    sales_rep_id: UUID = Field(..., description="Sales rep user ID to assign the lead to")


class AssignLeadResponse(BaseModel):
    """Response from lead assignment."""
    lead: Lead
    assigned_by: UUID = Field(..., description="User ID who made the assignment")
    assigned_at: str = Field(..., description="ISO timestamp of assignment")
    assigned_rep_name: Optional[str] = Field(None, description="Name of the assigned sales rep")


class UpdateLeadStatusRequest(BaseModel):
    """Request to update lead status."""
    status: str = Field(..., description="New lead status")
    reason: Optional[str] = Field(None, description="Optional reason for the change (audit)")


class MoveLeadStageRequest(BaseModel):
    """
    Request to move a lead forward to a new pipeline stage.

    **Pipeline order (forward only):**
    unqualified / service_not_offered / review (0) → qualified (1) → booked (2)
    → appointment (3) → appointment_ran (4) → won / lost (5)

    **Required fields per target_stage:**

    | target_stage    | Required fields                                                      |
    |-----------------|----------------------------------------------------------------------|
    | qualified       | *(none)*                                                             |
    | booked          | `scheduled_start`                                                    |
    | appointment     | `assigned_rep_id`; also `scheduled_start` if no appointment exists   |
    | appointment_ran | *(none)*                                                             |
    | won             | `deal_size`                                                          |
    | lost            | `reason`                                                             |
    """
    target_stage: str = Field(
        ...,
        description="Target pipeline stage. Allowed values: qualified, booked, appointment, appointment_ran, won, lost",
        json_schema_extra={"enum": ["qualified", "booked", "appointment", "appointment_ran", "won", "lost"]},
    )
    scheduled_start: Optional[datetime] = Field(
        None,
        description="Appointment date/time in ISO 8601 format. "
        "REQUIRED when target_stage='booked'. "
        "REQUIRED when target_stage='appointment' and no appointment exists for this lead.",
    )
    scheduled_end: Optional[datetime] = Field(
        None,
        description="Appointment end date/time in ISO 8601 (optional).",
    )
    location_address: Optional[str] = Field(
        None,
        description="Appointment location / service address (optional, e.g. '123 Main St, Phoenix AZ').",
    )
    assigned_rep_id: Optional[UUID] = Field(
        None,
        description="UUID of the sales rep to assign. REQUIRED when target_stage='appointment'. "
        "The rep must be an active user with role='sales_rep' in the same company.",
    )
    deal_size: Optional[float] = Field(
        None,
        description="Deal value in dollars. REQUIRED when target_stage='won'.",
    )
    reason: Optional[str] = Field(
        None,
        description="Reason / note for this move (optional). Stored in the audit log (lead_status_changes table).",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "summary": "Move to booked",
                    "value": {
                        "target_stage": "booked",
                        "scheduled_start": "2026-03-15T10:00:00Z",
                        "location_address": "123 Main St, Phoenix AZ",
                    },
                },
                {
                    "summary": "Move to appointment (assign rep)",
                    "value": {
                        "target_stage": "appointment",
                        "assigned_rep_id": "ae6e55d1-afc6-41b7-a12a-bc6cab51346b",
                    },
                },
                {
                    "summary": "Move to won",
                    "value": {
                        "target_stage": "won",
                        "deal_size": 12500.00,
                        "reason": "Customer signed contract",
                    },
                },
                {
                    "summary": "Move to lost",
                    "value": {
                        "target_stage": "lost",
                        "reason": "Customer chose a competitor",
                    },
                },
            ]
        }
    }


class MoveLeadStageResponse(BaseModel):
    """
    Response after successfully moving a lead to a new pipeline stage.

    Includes the updated lead object, the previous/new stage names,
    and flags indicating whether an appointment was created or updated as a side-effect.
    """
    lead: Lead = Field(..., description="The updated lead object after the stage move")
    previous_stage: Optional[str] = Field(None, description="Pipeline stage the lead was in before the move")
    new_stage: str = Field(..., description="Pipeline stage the lead is in now")
    appointment_created: bool = Field(
        False,
        description="True if a new appointment row was created (happens when moving to booked/appointment without an existing appointment)",
    )
    appointment_updated: bool = Field(
        False,
        description="True if an existing appointment was updated (e.g. rep assigned, or outcome set to won/lost)",
    )


@router.post("/{lead_id}/assign", response_model=AssignLeadResponse, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def assign_lead(
    lead_id: UUID,
    request: AssignLeadRequest,
    db: DbSession,
    # RBAC DISABLED - user: User = Depends(require_manager_or_csr),
    user: User = Depends(require_manager_or_csr),  # RBAC DISABLED - Returns dummy user
) -> AssignLeadResponse:
    """
    Assign a lead to a sales rep.
    
    A CSR or Executive can assign a lead to a sales rep. The assignment is tracked
    in the lead's metadata, including who assigned it and when.
    
    Access: EXECUTIVE, CSR
    """
    try:
        service = LeadService(db)
        
        # Assign the lead (user.id is the CSR/Executive making the assignment)
        assigned_lead = await service.assign_to_rep(
            lead_id=lead_id,
            sales_rep_id=request.sales_rep_id,
            assigned_by_user_id=user.id,
        )
        
        if not assigned_lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        # Extract assignment info from metadata
        assignment_info = assigned_lead.extra_metadata.get("last_assignment", {}) if assigned_lead.extra_metadata else {}
        assigned_at = assignment_info.get("assigned_at", "")
        
        # Get assigned rep name
        assigned_rep_name = None
        if assigned_lead.assigned_rep_id:
            from app.domain.users.service import UserService
            user_service = UserService(db)
            rep_user = await user_service.get_by_id(assigned_lead.assigned_rep_id)
            if rep_user:
                first_name = rep_user.first_name or ""
                last_name = rep_user.last_name or ""
                assigned_rep_name = f"{first_name} {last_name}".strip() or None
        
        return AssignLeadResponse(
            lead=assigned_lead,
            assigned_by=user.id,
            assigned_at=assigned_at,
            assigned_rep_name=assigned_rep_name,
        )
    except ValueError as e:
        # Validation error (e.g., sales rep not found, wrong company)
        logger.error(f"Validation error assigning lead: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning lead: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign lead: {str(e)}",
        )


@router.put("/{lead_id}/status", response_model=Lead, status_code=status.HTTP_200_OK, responses=RESPONSES)
async def update_lead_status(
    lead_id: UUID,
    request: UpdateLeadStatusRequest,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> Lead:
    """
    Update lead status.
    
    Updates the status of a lead. Valid status values are defined in LeadStatus enum.
    When called by an EXECUTIVE, the change is logged in lead_status_changes (audit).
    
    Access: EXECUTIVE (audit logged), CSR (no audit)
    
    Args:
        lead_id: Lead ID to update
        request: Status update request (status, optional reason)
    """
    try:
        from app.domain.enums import UserRole
        service = LeadService(db)
        # Log to audit table only when changed by executive (admin)
        changed_by = user.id if getattr(user, "role", None) == UserRole.EXECUTIVE.value else None
        updated_lead = await service.update_status(
            lead_id=lead_id,
            status=request.status,
            changed_by_user_id=changed_by,
            reason=request.reason,
        )
        
        if not updated_lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lead not found",
            )
        
        return updated_lead
    except ValueError as e:
        # Validation error (e.g., invalid status)
        logger.error(f"Validation error updating lead status: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update lead status: {str(e)}",
        )


@router.post(
    "/{lead_id}/move-stage",
    response_model=MoveLeadStageResponse,
    status_code=status.HTTP_200_OK,
    responses={
        **RESPONSES,
        200: {
            "description": "Lead successfully moved to the new pipeline stage",
            "content": {
                "application/json": {
                    "example": {
                        "lead": {
                            "id": "ede64a3e-cb73-44c4-94cc-35af4a95b0ac",
                            "status": "qualified_booked",
                            "deal_status": "booked",
                            "pipeline_stage": "booked",
                            "assigned_rep_id": None,
                            "deal_size": None,
                            "closed_at": None,
                        },
                        "previous_stage": "qualified",
                        "new_stage": "booked",
                        "appointment_created": True,
                        "appointment_updated": False,
                    }
                }
            },
        },
    },
    summary="Move lead forward in pipeline",
    tags=["Pipeline"],
)
async def move_lead_stage(
    lead_id: UUID,
    request: MoveLeadStageRequest,
    db: DbSession,
    user: User = Depends(require_manager_or_csr),
) -> MoveLeadStageResponse:
    """
    Move a lead **forward** through pipeline stages. Backward moves are rejected.

    ## Pipeline Stage Order

    | Order | Stages                                  |
    |-------|-----------------------------------------|
    | 0     | unqualified, service_not_offered, review |
    | 1     | qualified                               |
    | 2     | booked                                  |
    | 3     | appointment                             |
    | 4     | appointment_ran                         |
    | 5     | won, lost                               |

    Skipping stages is allowed (e.g. qualified → won).

    ## Required Fields Per Target Stage

    | target_stage     | Required                       | Side-effects                                  |
    |------------------|--------------------------------|-----------------------------------------------|
    | **qualified**    | —                              | Lead status → qualified_unbooked              |
    | **booked**       | `scheduled_start`              | Creates appointment if none exists            |
    | **appointment**  | `assigned_rep_id`              | Assigns rep; creates/updates appointment      |
    | **appointment_ran** | —                           | —                                             |
    | **won**          | `deal_size`                    | Sets closed_at; appointment outcome → won     |
    | **lost**         | — (`reason` optional)          | Sets closed_at; appointment outcome → lost    |

    ## Error Responses (400)

    - `"Cannot move backward from 'won' to 'booked'. Only forward movement is allowed."`
    - `"scheduled_start is required when moving to 'booked'"`
    - `"assigned_rep_id is required when moving to 'appointment'"`
    - `"deal_size is required when moving to 'won'"`
    - `"Sales rep with ID ... not found or not active"`
    - `"Lead and sales rep must belong to the same company"`

    ## Audit

    Every move is logged to the `lead_status_changes` table with old/new status,
    old/new deal_status, the user who made the change, and an optional reason.
    """
    try:
        service = LeadService(db)
        result = await service.move_pipeline_stage(
            lead_id=lead_id,
            target_stage=request.target_stage,
            changed_by_user_id=user.id,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            location_address=request.location_address,
            assigned_rep_id=request.assigned_rep_id,
            deal_size=request.deal_size,
            reason=request.reason,
        )
        return result
    except ValueError as e:
        logger.error(f"Validation error moving lead stage: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error moving lead stage: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to move lead stage: {str(e)}",
        )

