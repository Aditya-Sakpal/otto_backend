"""
Follow-up agent: approve and send a proposed follow_up_otto draft (manual review flow).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.dependencies import DbSession
from app.core.logging import get_logger
from app.core.permissions import require_any_role
from app.domain.enums import UserRole
from app.domain.schemas.follow_up import (
    FollowUpOttoApproveSendRequest,
    FollowUpOttoApproveSendResponse,
)
from app.domain.users.models import User
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.follow_up_otto import FollowUpOttoORM
from app.infrastructure.database.models.lead import LeadORM

logger = get_logger(__name__)

router = APIRouter()

_AGENTS_ROOT = Path(__file__).resolve().parents[2] / "agents"
_agents_path = str(_AGENTS_ROOT)
if _agents_path not in sys.path:
    sys.path.insert(0, _agents_path)

from contextual_follow_up_agent.config.company_config import CompanyConfigStore
from contextual_follow_up_agent.config.settings import settings as agent_fu_settings
from contextual_follow_up_agent.executor.pending_action import create_rep_nudge
from contextual_follow_up_agent.executor.twilio_sms import TwilioSMSSender
from contextual_follow_up_agent.db.local import get_local_session, init_local_db
from contextual_follow_up_agent.models.output import ObjectionResponse, RepNudge

RESPONSES = {
    400: {"description": "Bad request"},
    403: {"description": "Forbidden"},
    404: {"description": "Not found"},
    500: {"description": "Server error"},
}


def _rep_nudge_from_row(row: FollowUpOttoORM) -> RepNudge:
    objections: list[ObjectionResponse] = []
    raw = row.objections
    if isinstance(raw, list):
        for o in raw:
            if isinstance(o, dict):
                objections.append(
                    ObjectionResponse(
                        objection=str(o.get("objection", "")),
                        suggested_response=str(
                            o.get("suggested_response", o.get("response", ""))
                        ),
                    )
                )
    ktp_raw = row.key_talking_points
    if isinstance(ktp_raw, list):
        ktp_list = [str(x) for x in ktp_raw]
    else:
        ktp_list = []
    return RepNudge(
        opening_line=row.opening_line or "",
        objections=objections,
        close_approach=row.close_approach or "",
        key_talking_points=ktp_list,
    )


async def _sync_sqlite_follow_up_log(
    log_id: UUID,
    *,
    message_content: str,
    status: str,
    sent_at: datetime | None,
    pending_action_id: UUID | str | None,
    error_message: str | None,
) -> None:
    """
    Keep agent SQLite follow_up_log aligned with Postgres after manual approve-send.

    Best-effort: logs and swallows errors if the API process cannot reach the agent DB file.
    """
    pid: str | None = None
    if pending_action_id is not None:
        pid = (
            pending_action_id
            if isinstance(pending_action_id, str)
            else str(pending_action_id)
        )

    try:
        await init_local_db()
        local = await get_local_session()
        try:
            await local.execute(
                text("""
                    UPDATE follow_up_log
                    SET message_content = :message_content,
                        status = :status,
                        sent_at = :sent_at,
                        pending_action_id = :pending_action_id,
                        error_message = :error_message,
                        updated_at = :updated_at
                    WHERE id = :id
                """),
                {
                    "id": str(log_id),
                    "message_content": message_content,
                    "status": status,
                    "sent_at": sent_at.isoformat() if sent_at else None,
                    "pending_action_id": pid,
                    "error_message": error_message,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await local.commit()
        finally:
            await local.close()
    except Exception as e:
        logger.warning(
            "Could not sync SQLite follow_up_log after manual approve-send",
            log_id=str(log_id),
            error=str(e),
        )


async def _latest_appointment_id_for_lead(db: DbSession, lead_id: UUID) -> UUID | None:
    res = await db.execute(
        select(AppointmentORM.id)
        .where(AppointmentORM.lead_id == lead_id)
        .order_by(AppointmentORM.scheduled_start.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


@router.post(
    "/otto-proposals/{follow_up_id}/approve-send",
    response_model=FollowUpOttoApproveSendResponse,
    responses=RESPONSES,
)
async def approve_send_follow_up_otto(
    follow_up_id: UUID,
    company_id: UUID = Query(..., description="Company UUID"),
    body: FollowUpOttoApproveSendRequest = Body(default_factory=FollowUpOttoApproveSendRequest),
    db: DbSession = ...,
    current_user: User = Depends(
        require_any_role([UserRole.SALES_REP, UserRole.EXECUTIVE]),
    ),
):
    """
    Send a **proposed** contextual follow-up (SMS to lead or rep nudge task).

    Call after the user previews the draft (e.g. from appointment context) and clicks Send.
    Optional **message_content** replaces the stored draft for this send only.

    **Example request body** (optional — omit or `{}` to send the stored draft unchanged)

    ```json
    { "message_content": "Hi — confirming we can meet Tuesday at 2pm." }
    ```

    **Example response (200)** — SMS sent (Twilio SID when applicable)

    ```json
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "status": "sent",
      "external_message_id": "SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "pending_action_id": null,
      "error_message": null
    }
    ```

    **Example response (200)** — rep nudge created instead of SMS

    ```json
    {
      "id": "4fa85f64-5717-4562-b3fc-2c963f66afa7",
      "status": "sent",
      "external_message_id": null,
      "pending_action_id": "8d8f8f8f-8d8f-8d8f-8d8f-8d8f8f8f8d8f",
      "error_message": null
    }
    ```
    """
    if current_user.company_id and current_user.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    row = await db.get(FollowUpOttoORM, follow_up_id)
    if not row or row.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follow-up draft not found",
        )

    if row.status != "proposed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Only proposed drafts can be approved to send; this row is status={row.status!r}. "
                "Run the contextual follow-up agent again (with manual review on) for a new draft, "
                "or pick another follow_up_otto id where status is 'proposed'."
            ),
        )

    base = (
        body.message_content
        if body.message_content is not None
        else row.message_content
    )
    text_to_send = (base or "").strip()
    if not text_to_send:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message_content is empty",
        )

    row.message_content = text_to_send
    await db.flush()

    if row.action_type == "sms_to_lead":
        stmt = (
            select(LeadORM)
            .options(selectinload(LeadORM.contact_card))
            .where(LeadORM.id == row.lead_id)
        )
        res = await db.execute(stmt)
        lead = res.scalar_one_or_none()
        phone = (
            lead.contact_card.primary_phone
            if lead and lead.contact_card
            else None
        )
        if not phone:
            row.status = "failed"
            row.error_message = "No phone number on lead"
            row.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await _sync_sqlite_follow_up_log(
                follow_up_id,
                message_content=text_to_send,
                status="failed",
                sent_at=None,
                pending_action_id=None,
                error_message="No phone number on lead",
            )
            return FollowUpOttoApproveSendResponse(
                id=row.id,
                status=row.status,
                error_message=row.error_message,
            )

        company_config = CompanyConfigStore().get(str(company_id))
        if (
            not agent_fu_settings.TWILIO_ACCOUNT_SID
            or not agent_fu_settings.TWILIO_AUTH_TOKEN
            or not company_config
        ):
            row.status = "failed"
            row.error_message = "Twilio or company SMS config not available"
            row.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await _sync_sqlite_follow_up_log(
                follow_up_id,
                message_content=text_to_send,
                status="failed",
                sent_at=None,
                pending_action_id=None,
                error_message="Twilio or company SMS config not available",
            )
            return FollowUpOttoApproveSendResponse(
                id=row.id,
                status=row.status,
                error_message=row.error_message,
            )

        sms_sender = TwilioSMSSender(
            agent_fu_settings.TWILIO_ACCOUNT_SID,
            agent_fu_settings.TWILIO_AUTH_TOKEN,
        )
        source_metadata = {
            "source": "contextual-follow-up-agent",
            "follow_up_otto_id": str(row.id),
            "attempt_number": row.attempt_number,
            "queue_type": row.queue_type,
            "approved_manually": True,
        }
        sid = await sms_sender.send(
            to=phone,
            from_=company_config.twilio_from_number,
            body=text_to_send,
            source_metadata=source_metadata,
        )
        now = datetime.now(timezone.utc)
        if sid:
            row.status = "sent"
            row.sent_at = now
            row.external_message_id = sid
            row.error_message = None
        else:
            row.status = "failed"
            row.error_message = "Twilio send failed"
        row.updated_at = now
        await db.commit()
        await db.refresh(row)
        await _sync_sqlite_follow_up_log(
            follow_up_id,
            message_content=text_to_send,
            status=row.status,
            sent_at=row.sent_at,
            pending_action_id=None,
            error_message=row.error_message,
        )
        return FollowUpOttoApproveSendResponse(
            id=row.id,
            status=row.status,
            external_message_id=row.external_message_id,
            error_message=row.error_message,
        )

    if row.action_type == "nudge_sales_rep":
        if not row.assigned_rep_id:
            row.status = "failed"
            row.error_message = "No assigned rep for nudge"
            row.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await _sync_sqlite_follow_up_log(
                follow_up_id,
                message_content=text_to_send,
                status="failed",
                sent_at=None,
                pending_action_id=None,
                error_message="No assigned rep for nudge",
            )
            return FollowUpOttoApproveSendResponse(
                id=row.id,
                status=row.status,
                error_message=row.error_message,
            )

        appointment_id = await _latest_appointment_id_for_lead(db, row.lead_id)
        nudge = _rep_nudge_from_row(row)
        action_id = await create_rep_nudge(
            db,
            company_id=row.company_id,
            lead_id=row.lead_id,
            appointment_id=appointment_id,
            owner_id=row.assigned_rep_id,
            raw_text=text_to_send,
            nudge=nudge,
            due_at=row.scheduled_at,
            attempt_number=row.attempt_number,
            queue_type=row.queue_type,
        )
        now = datetime.now(timezone.utc)
        row = await db.get(FollowUpOttoORM, follow_up_id)
        if not row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Row missing after pending_action insert",
            )
        if action_id:
            row.status = "sent"
            row.sent_at = now
            row.pending_action_id = UUID(action_id)
            row.error_message = None
        else:
            row.status = "failed"
            row.error_message = "pending_action INSERT failed"
        row.updated_at = now
        await db.commit()
        await db.refresh(row)
        await _sync_sqlite_follow_up_log(
            follow_up_id,
            message_content=text_to_send,
            status=row.status,
            sent_at=row.sent_at,
            pending_action_id=row.pending_action_id,
            error_message=row.error_message,
        )
        return FollowUpOttoApproveSendResponse(
            id=row.id,
            status=row.status,
            pending_action_id=row.pending_action_id,
            error_message=row.error_message,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported action_type: {row.action_type}",
    )
