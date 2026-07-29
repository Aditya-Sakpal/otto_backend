"""
Queue 2 scanner: Appointment Ran, Pending Close.

Finds leads where the sales rep ran the in-person appointment
but didn't close. Not marked as won or lost.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)

SCAN_SQL = text("""
    SELECT
        l.id                            AS lead_id,
        l.company_id,
        l.pipeline_stage,
        l.status                        AS lead_status,
        l.assigned_rep_id,
        a.id                            AS appointment_id,
        a.scheduled_start,
        a.outcome,
        a.summary                       AS appt_summary,
        a.objections                    AS appt_objections,
        a.objection_texts               AS appt_objection_texts,
        a.key_points                    AS appt_key_points,
        a.action_items                  AS appt_action_items,
        a.next_steps                    AS appt_next_steps,
        a.sentiment_score               AS appt_sentiment,
        a.pending_actions_data          AS appt_pending_actions,
        cc.first_name,
        cc.last_name,
        cc.primary_phone,
        cc.address,
        cc.city,
        cc.state,
        cc.postal_code,
        cc.property_snapshot,
        co.name                         AS company_name,
        ca.summary                      AS call_summary,
        ca.pending_actions              AS call_pending_actions,
        ca.objection_texts              AS call_objection_texts,
        ca.service_requested,
        ca.property_details,
        ca.qualification_overall_score,
        ca.sentiment_score              AS call_sentiment,
        ca.bant_need_score,
        ca.bant_budget_score,
        ca.bant_timeline_score,
        ca.bant_authority_score
    FROM leads l
    JOIN appointments a ON a.lead_id = l.id
    JOIN contact_cards cc ON l.contact_card_id = cc.id
    JOIN companies co ON l.company_id = co.id
    LEFT JOIN call_analyses ca ON ca.call_id = a.interaction_id
    WHERE l.pipeline_stage = 'appointment_ran'
      AND (a.outcome IS NULL OR a.outcome NOT IN ('won', 'lost'))
    ORDER BY a.scheduled_start DESC
""")


async def scan_appointment_ran(session: AsyncSession) -> list[dict]:
    """
    Scan for appointment-ran leads with their analysis data.

    Returns list of row dicts ready for context assembly.
    """
    result = await session.execute(SCAN_SQL)
    rows = result.mappings().all()
    logger.info("Queue 2 scan complete", leads_found=len(rows))
    return [dict(r) for r in rows]
