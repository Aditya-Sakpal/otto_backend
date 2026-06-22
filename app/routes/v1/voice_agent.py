"""Retell AI voice-agent tool endpoints (public, shared-secret auth)."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.voice_agent_auth import verify_voice_agent_secret
from app.domain.schemas.voice_agent import (
    AvailableSlotsResponse,
    CreateAppointmentResponse,
    CreateLeadResponse,
    CurrentDateResponse,
    CustomerHistoryResponse,
    GenerateFollowupResponse,
    GenericStatusResponse,
    SaveCallSummaryResponse,
    SearchLeadResponse,
    SurfaceNextActionsResponse,
)
from app.services.voice_agent_service import (
    VoiceAgentService,
    parse_company_id,
    parse_retell_payload,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/voice-agent",
    tags=["voice-agent"],
    dependencies=[Depends(verify_voice_agent_secret)],
)


async def _parse_body(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return parse_retell_payload(body)


@router.post("/search_lead", response_model=SearchLeadResponse)
async def search_lead(
    request: Request,
    db: DbSession,
    call_id: Optional[str] = Query(None),
) -> SearchLeadResponse:
    args, call = await _parse_body(request)
    if call_id and not call.get("call_id"):
        call["call_id"] = call_id
    try:
        svc = VoiceAgentService(db)
        return await svc.search_lead(args, call)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/get_customer_history", response_model=CustomerHistoryResponse)
async def get_customer_history(request: Request, db: DbSession) -> CustomerHistoryResponse:
    args, call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).get_customer_history(args, call)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create_lead", response_model=CreateLeadResponse)
async def create_lead(
    request: Request,
    db: DbSession,
    call_id: Optional[str] = Query(None),
) -> CreateLeadResponse:
    args, call = await _parse_body(request)
    if call_id:
        call["call_id"] = call_id
    try:
        return await VoiceAgentService(db).create_lead(args, call, call_id=call_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/save_property_details", response_model=GenericStatusResponse)
async def save_property_details(request: Request, db: DbSession) -> GenericStatusResponse:
    args, call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).save_property_details(args, call)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/update_lead", response_model=GenericStatusResponse)
async def update_lead(request: Request, db: DbSession) -> GenericStatusResponse:
    args, call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).update_lead(args, call)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/get_current_date", response_model=CurrentDateResponse)
async def get_current_date(
    db: DbSession,
    company_id: Optional[str] = Query(None),
) -> CurrentDateResponse:
    try:
        cid = parse_company_id(company_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await VoiceAgentService(db).get_current_date(cid)


@router.get("/get_available_slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    db: DbSession,
    company_id: Optional[str] = Query(None),
    slot_date: str = Query(..., alias="date"),
    assigned_rep_id: Optional[str] = Query(None),
) -> AvailableSlotsResponse:
    try:
        cid = parse_company_id(company_id)
        target = date.fromisoformat(slot_date)
        rep = UUID(assigned_rep_id) if assigned_rep_id else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await VoiceAgentService(db).get_available_slots(cid, target, rep)


@router.post("/create_appointment", response_model=CreateAppointmentResponse)
async def create_appointment(
    request: Request,
    db: DbSession,
    call_id: Optional[str] = Query(None),
) -> CreateAppointmentResponse:
    args, call = await _parse_body(request)
    if call_id:
        call["call_id"] = call_id
    try:
        return await VoiceAgentService(db).create_appointment(args, call, call_id=call_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/create_pending_action", response_model=GenericStatusResponse)
async def create_pending_action(
    request: Request,
    db: DbSession,
    call_id: Optional[str] = Query(None),
) -> GenericStatusResponse:
    args, call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).create_pending_action(args, call, call_id=call_id)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/generate_followup", response_model=GenerateFollowupResponse, status_code=202)
async def generate_followup(request: Request, db: DbSession) -> GenerateFollowupResponse:
    args, _call = await _parse_body(request)

    async def _run() -> None:
        from app.infrastructure.database.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                await VoiceAgentService(session).generate_followup(args)
            except Exception as exc:
                logger.error("Background generate_followup failed", error=str(exc))

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        await _run()
    return GenerateFollowupResponse(status="queued")


@router.post("/surface_next_actions", response_model=SurfaceNextActionsResponse)
async def surface_next_actions(request: Request, db: DbSession) -> SurfaceNextActionsResponse:
    args, _call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).surface_next_actions(args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/send_sms", response_model=GenericStatusResponse)
async def send_sms(request: Request, db: DbSession) -> GenericStatusResponse:
    args, _call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).send_sms(args)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/send_email", response_model=GenericStatusResponse)
async def send_email(request: Request, db: DbSession) -> GenericStatusResponse:
    args, _call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).send_email(args)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/save_call_summary", response_model=SaveCallSummaryResponse)
async def save_call_summary(
    request: Request,
    db: DbSession,
    call_id: Optional[str] = Query(None),
) -> SaveCallSummaryResponse:
    args, call = await _parse_body(request)
    if call_id:
        call["call_id"] = call_id
    try:
        return await VoiceAgentService(db).save_call_summary(args, call)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/save_recording_analysis", response_model=GenericStatusResponse)
async def save_recording_analysis(request: Request, db: DbSession) -> GenericStatusResponse:
    args, _call = await _parse_body(request)
    try:
        return await VoiceAgentService(db).save_recording_analysis(args)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
