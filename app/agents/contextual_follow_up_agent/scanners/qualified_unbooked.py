"""
Queue 1 scanner: Qualified Unbooked leads.

Finds leads where CSR qualified the lead but no appointment was booked.
Joins to call_analyses via the most recent call for each lead.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from contextual_follow_up_agent.config.logging import get_logger

logger = get_logger(__name__)

SCAN_SQL = text("""
    SELECT
        l.id                        AS lead_id,
        l.company_id,
        l.pipeline_stage,
        l.status                    AS lead_status,
        l.assigned_rep_id,
        l.created_at                AS lead_created_at,
        cc.first_name,
        cc.last_name,
        cc.primary_phone,
        cc.address,
        cc.city,
        cc.state,
        cc.postal_code,
        cc.property_snapshot,
        co.name                     AS company_name,
        ca.summary,
        ca.key_points,
        ca.action_items,
        ca.next_steps,
        ca.pending_actions,
        ca.objections,
        ca.objection_texts,
        ca.objections_total_count,
        ca.sentiment_score,
        ca.qualification_status,
        ca.booking_status,
        ca.service_requested,
        ca.property_details,
        ca.follow_up_required,
        ca.follow_up_reason,
        ca.bant_need_score,
        ca.bant_budget_score,
        ca.bant_timeline_score,
        ca.bant_authority_score,
        ca.qualification_overall_score
    FROM leads l
    JOIN contact_cards cc ON l.contact_card_id = cc.id
    JOIN companies co ON l.company_id = co.id
    LEFT JOIN LATERAL (
        SELECT c.id AS call_id
        FROM calls c
        WHERE c.lead_id = l.id
        ORDER BY c.created_at DESC
        LIMIT 1
    ) latest_call ON TRUE
    LEFT JOIN call_analyses ca ON ca.call_id = latest_call.call_id
    WHERE l.pipeline_stage = 'qualified'
      AND l.status = 'qualified_unbooked'
""")


async def scan_qualified_unbooked(session: AsyncSession) -> list[dict]:
    """
    Scan for qualified unbooked leads with their analysis data.

    Returns list of row dicts ready for context assembly.
    """
    result = await session.execute(SCAN_SQL)
    rows = result.mappings().all()
    logger.info("Queue 1 scan complete", leads_found=len(rows))
    return [dict(r) for r in rows]
