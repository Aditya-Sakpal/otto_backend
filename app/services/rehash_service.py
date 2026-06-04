"""
Rehash service.

Materializes missed-revenue opportunities as `pending_actions` rows (action_type
/ source == "rehash") across three categories, delivered through the existing
1-minute follow-up notification job with DB-backed idempotency. Mirrors the shape
of appointment_reminder_service.py — no new tables, services, or event buses.

Categories (extra_metadata.rehash_category):
  - qualified_unbooked  : qualified lead never booked, gone quiet
  - appointment_pending : appointment ran but outcome never closed
  - stale_lead          : open-pipeline lead with no activity for a while

Eligibility/age thresholds are configurable in core.config (REHASH_*).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.enums import PendingActionStatus
from app.domain.models.pending_action import PendingAction
from app.infrastructure.repositories.pending_action import PendingActionRepository

logger = get_logger(__name__)

UTC = timezone.utc

ACTION_TYPE = PendingActionRepository.REHASH_ACTION_TYPE  # "rehash"
SOURCE = PendingActionRepository.REHASH_SOURCE  # "rehash"
RULE_VERSION = "1"

CATEGORY_QUALIFIED_UNBOOKED = "qualified_unbooked"
CATEGORY_APPOINTMENT_PENDING = "appointment_pending"
CATEGORY_STALE_LEAD = "stale_lead"

ALL_CATEGORIES = (
    CATEGORY_QUALIFIED_UNBOOKED,
    CATEGORY_APPOINTMENT_PENDING,
    CATEGORY_STALE_LEAD,
)

REHASH_PRIORITY = 2

# Actions whose presence (pending) suppresses a new rehash for the same lead.
_NOISE_SUPPRESSION_TYPES = ("call_back", "follow_up")

# Global exclusions shared by all categories.
_EXCLUDED_STAGES = ("won", "lost", "service_not_offered", "unqualified", "review")
_EXCLUDED_STATUSES = (
    "closed_won",
    "closed_lost",
    "abandoned",
    "dormant",
    "qualified_service_not_offered",
)

_RAW_TEXT = {
    CATEGORY_QUALIFIED_UNBOOKED: "Rehash: qualified lead never booked — reach out to schedule",
    CATEGORY_APPOINTMENT_PENDING: "Rehash: appointment ran but outcome is still open — close it out",
    CATEGORY_STALE_LEAD: "Rehash: lead has gone quiet — re-engage before it goes cold",
}


@dataclass
class SyncResult:
    """Outcome of scan_and_sync_rehash."""
    scanned: int = 0
    created: int = 0
    cancelled: int = 0
    skipped: int = 0
    by_category: dict[str, int] = field(default_factory=dict)

    def _bump(self, category: str) -> None:
        self.by_category[category] = self.by_category.get(category, 0) + 1


# ── Pure eligibility predicates (unit-testable; SQL mirrors these) ────────

def compute_last_activity(
    lead_updated_at: Optional[datetime],
    lead_created_at: datetime,
    last_call_at: Optional[datetime] = None,
    last_appointment_at: Optional[datetime] = None,
) -> datetime:
    """GREATEST of lead update/create, latest call, latest appointment (UTC)."""
    candidates = [lead_updated_at or lead_created_at]
    if last_call_at:
        candidates.append(last_call_at)
    if last_appointment_at:
        candidates.append(last_appointment_at)
    return max(_aware(c) for c in candidates)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _excluded(stage: Optional[str], status: Optional[str]) -> bool:
    return (stage in _EXCLUDED_STAGES) or (status in _EXCLUDED_STATUSES)


def is_eligible_qualified_unbooked(
    *,
    status: Optional[str],
    pipeline_stage: Optional[str],
    last_update: datetime,
    has_future_pending_appointment: bool,
    now: datetime,
) -> bool:
    if _excluded(pipeline_stage, status):
        return False
    if status != "qualified_unbooked" or pipeline_stage != "qualified":
        return False
    if has_future_pending_appointment:
        return False
    age = now - timedelta(days=settings.REHASH_QUALIFIED_UNBOOKED_DAYS)
    return _aware(last_update) < age


def is_eligible_appointment_pending(
    *,
    pipeline_stage: Optional[str],
    appointment_outcome: Optional[str],
    scheduled_start: datetime,
    now: datetime,
) -> bool:
    if pipeline_stage != "appointment_ran":
        return False
    outcome = (appointment_outcome or "pending").lower()
    if outcome != "pending":
        return False
    age = now - timedelta(days=settings.REHASH_APPOINTMENT_PENDING_DAYS)
    return _aware(scheduled_start) < age


def is_eligible_stale_lead(
    *,
    status: Optional[str],
    pipeline_stage: Optional[str],
    last_activity: datetime,
    now: datetime,
) -> bool:
    if _excluded(pipeline_stage, status):
        return False
    if pipeline_stage not in ("qualified", "booked", "appointment"):
        return False
    age = now - timedelta(days=settings.REHASH_STALE_LEAD_DAYS)
    return _aware(last_activity) < age


# ── Candidate SQL (Postgres) ─────────────────────────────────────────────

_SQL_QUALIFIED_UNBOOKED = text(
    """
    SELECT l.id AS lead_id, l.company_id, l.assigned_rep_id
    FROM leads l
    WHERE l.status = 'qualified_unbooked'
      AND l.pipeline_stage = 'qualified'
      AND COALESCE(l.updated_at, l.created_at) < (now() AT TIME ZONE 'utc') - make_interval(days => :days)
      AND (CAST(:company_id AS uuid) IS NULL OR l.company_id = CAST(:company_id AS uuid))
      AND (CAST(:lead_id AS uuid) IS NULL OR l.id = CAST(:lead_id AS uuid))
      AND NOT EXISTS (
        SELECT 1 FROM appointments a
        WHERE a.lead_id = l.id
          AND a.scheduled_start > now()
          AND LOWER(COALESCE(a.outcome, 'pending')) = 'pending'
      )
    """
)

_SQL_APPOINTMENT_PENDING = text(
    """
    SELECT DISTINCT ON (l.id)
           l.id AS lead_id, l.company_id, l.assigned_rep_id, a.id AS appointment_id
    FROM leads l
    JOIN appointments a ON a.lead_id = l.id
    WHERE l.pipeline_stage = 'appointment_ran'
      AND LOWER(COALESCE(a.outcome, 'pending')) = 'pending'
      AND a.scheduled_start < (now() AT TIME ZONE 'utc') - make_interval(days => :days)
      AND (CAST(:company_id AS uuid) IS NULL OR l.company_id = CAST(:company_id AS uuid))
      AND (CAST(:lead_id AS uuid) IS NULL OR l.id = CAST(:lead_id AS uuid))
    ORDER BY l.id, a.scheduled_start DESC
    """
)

_SQL_STALE_LEAD = text(
    """
    WITH activity AS (
      SELECT l.id AS lead_id, l.company_id, l.assigned_rep_id,
        GREATEST(
          COALESCE(l.updated_at, l.created_at),
          COALESCE((SELECT MAX(c.created_at) FROM calls c WHERE c.lead_id = l.id), '-infinity'::timestamptz),
          COALESCE((SELECT MAX(COALESCE(a.updated_at, a.created_at)) FROM appointments a WHERE a.lead_id = l.id), '-infinity'::timestamptz)
        ) AS last_activity
      FROM leads l
      WHERE l.pipeline_stage IN ('qualified','booked','appointment')
        AND l.status NOT IN ('closed_won','closed_lost','abandoned','dormant','qualified_service_not_offered')
        AND l.pipeline_stage NOT IN ('won','lost','service_not_offered','unqualified','review')
        AND (CAST(:company_id AS uuid) IS NULL OR l.company_id = CAST(:company_id AS uuid))
        AND (CAST(:lead_id AS uuid) IS NULL OR l.id = CAST(:lead_id AS uuid))
    )
    SELECT lead_id, company_id, assigned_rep_id
    FROM activity
    WHERE last_activity < (now() AT TIME ZONE 'utc') - make_interval(days => :days)
    """
)

_CATEGORY_SQL = {
    CATEGORY_QUALIFIED_UNBOOKED: (_SQL_QUALIFIED_UNBOOKED, "REHASH_QUALIFIED_UNBOOKED_DAYS"),
    CATEGORY_APPOINTMENT_PENDING: (_SQL_APPOINTMENT_PENDING, "REHASH_APPOINTMENT_PENDING_DAYS"),
    CATEGORY_STALE_LEAD: (_SQL_STALE_LEAD, "REHASH_STALE_LEAD_DAYS"),
}


async def _fetch_candidates(
    session: AsyncSession,
    category: str,
    company_id: Optional[UUID],
    lead_id: Optional[UUID],
) -> list[dict[str, Any]]:
    sql, days_attr = _CATEGORY_SQL[category]
    days = getattr(settings, days_attr)
    result = await session.execute(
        sql,
        {
            "days": days,
            "company_id": str(company_id) if company_id else None,
            "lead_id": str(lead_id) if lead_id else None,
        },
    )
    return [dict(row._mapping) for row in result]


def _build_row(
    *,
    company_id: UUID,
    lead_id: UUID,
    owner_id: Optional[UUID],
    category: str,
    appointment_id: Optional[UUID],
    now: datetime,
) -> PendingAction:
    meta: dict[str, Any] = {
        "rehash_category": category,
        "detected_at": now.isoformat(),
        "rule_version": RULE_VERSION,
    }
    if appointment_id is not None:
        meta["appointment_id"] = str(appointment_id)
    return PendingAction(
        company_id=company_id,
        lead_id=lead_id,
        appointment_id=appointment_id,
        action_type=ACTION_TYPE,
        raw_text=_RAW_TEXT[category],
        status=PendingActionStatus.PENDING,
        due_at=now,
        priority=REHASH_PRIORITY,
        owner_id=owner_id,
        source=SOURCE,
        extra_metadata=meta,
    )


async def scan_and_sync_rehash(
    session: AsyncSession,
    *,
    company_id: Optional[UUID] = None,
    lead_id: Optional[UUID] = None,
    suppress_with_existing_actions: bool = True,
) -> SyncResult:
    """Scan for rehash opportunities and reconcile pending_actions.

    Creates one pending rehash row per (lead, category) for eligible leads, and
    cancels pending rehash rows whose lead is no longer eligible for that
    category. Idempotent: a second run creates 0 new rows. Caller owns the commit.

    Scope it with `company_id` (staged rollout) and/or `lead_id` (single-lead
    re-sync, e.g. after a status change). When `lead_id` is given, cancellation
    is also restricted to that lead so other leads' rows are never touched.
    """
    result = SyncResult()
    now = datetime.now(UTC)
    repo = PendingActionRepository(session)

    # eligible_by_category[category] = set of lead_ids currently eligible
    eligible_by_category: dict[str, set[UUID]] = {c: set() for c in ALL_CATEGORIES}

    # 1. Gather all candidates up front so the two suppression checks can be
    #    batched into a single query each (was a per-candidate N+1 — ~2 round
    #    trips × 1000s of candidates, which timed out on large tenants).
    candidates_by_category: dict[str, list[dict]] = {}
    all_lead_ids: set[UUID] = set()
    for category in ALL_CATEGORIES:
        cands = await _fetch_candidates(session, category, company_id, lead_id)
        candidates_by_category[category] = cands
        for cand in cands:
            cand_lead_id = cand["lead_id"]
            eligible_by_category[category].add(cand_lead_id)
            all_lead_ids.add(cand_lead_id)

    lead_id_list = list(all_lead_ids)

    # 2. Batch the suppression sets once for the whole candidate population.
    active_rehash_by_lead = await repo.active_rehash_categories_for_leads(lead_id_list)
    noise_leads: set[UUID] = set()
    if suppress_with_existing_actions:
        noise_leads = await repo.leads_with_pending_action_of_types(
            lead_id_list, _NOISE_SUPPRESSION_TYPES
        )

    # 3. Decide per candidate using in-memory set lookups (no per-lead queries),
    #    collecting new rows for a single bulk insert (per-row create against a
    #    remote DB is too slow for ~1k-row scans).
    rows_to_create: list[PendingAction] = []
    for category in ALL_CATEGORIES:
        for cand in candidates_by_category[category]:
            result.scanned += 1
            cand_lead_id = cand["lead_id"]

            # Idempotency / no re-nag: one rehash per (lead, category) per
            # eligibility episode. A pending OR completed (already-notified)
            # rehash suppresses re-creation; the episode is closed only when the
            # lead leaves eligibility (see _cancel_ineligible).
            if category in active_rehash_by_lead.get(cand_lead_id, ()):
                result.skipped += 1
                continue

            # Noise reduction: skip if a pending call_back/follow_up already
            # covers the same revenue intent.
            if cand_lead_id in noise_leads:
                result.skipped += 1
                continue

            rows_to_create.append(_build_row(
                company_id=cand["company_id"],
                lead_id=cand_lead_id,
                owner_id=cand.get("assigned_rep_id"),
                category=category,
                appointment_id=cand.get("appointment_id"),
                now=now,
            ))
            result._bump(category)

    if rows_to_create:
        result.created = await repo.bulk_create(rows_to_create)

    # Cancel stale pending rehash rows: any pending rehash whose lead is no
    # longer in the eligible set for that category.
    cancelled = await _cancel_ineligible(
        session, repo, eligible_by_category, company_id, lead_id
    )
    result.cancelled = cancelled

    logger.info(
        "Rehash scan complete",
        scanned=result.scanned,
        created=result.created,
        cancelled=result.cancelled,
        skipped=result.skipped,
        by_category=result.by_category,
    )
    return result


async def _cancel_ineligible(
    session: AsyncSession,
    repo: PendingActionRepository,
    eligible_by_category: dict[str, set[UUID]],
    company_id: Optional[UUID],
    lead_id: Optional[UUID],
) -> int:
    """Close rehash rows whose lead is no longer eligible per category.

    Considers pending AND completed rows: an ineligible lead's episode is closed
    so a future re-eligibility creates a fresh rehash. Eligible leads keep their
    pending/completed rows (the latter suppresses re-nagging).

    Scope mirrors the scan: when company_id/lead_id are given, only matching rows
    are considered so out-of-scope leads are never touched.
    """
    import json

    where_company = "AND company_id = CAST(:company_id AS uuid)" if company_id else ""
    where_lead = "AND lead_id = CAST(:lead_id AS uuid)" if lead_id else ""
    rows = await session.execute(
        text(
            f"""
            SELECT id, lead_id, extra_metadata
            FROM pending_actions
            WHERE action_type = 'rehash' AND source = 'rehash'
              AND status IN ('pending', 'completed')
            {where_company}
            {where_lead}
            """
        ),
        {
            "company_id": str(company_id) if company_id else None,
            "lead_id": str(lead_id) if lead_id else None,
        },
    )
    to_cancel: list[str] = []
    for row in rows:
        m = row._mapping
        meta = m["extra_metadata"] or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        category = meta.get("rehash_category")
        row_lead_id = m["lead_id"]
        if category not in eligible_by_category:
            continue
        if row_lead_id in eligible_by_category[category]:
            continue
        # Lead no longer eligible for this category → close the episode.
        to_cancel.append(str(m["id"]))

    if to_cancel:
        # Single UPDATE for the whole stale batch (was a per-row UPDATE loop).
        await session.execute(
            text(
                "UPDATE pending_actions SET status = 'cancelled' "
                "WHERE id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"ids": to_cancel},
        )
        await session.flush()
    return len(to_cancel)
