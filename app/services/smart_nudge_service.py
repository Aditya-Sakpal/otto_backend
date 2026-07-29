"""
Smart Nudge Service.

Generates AI-driven coaching nudges by evaluating rep performance:
- Compares current metrics against coaching cycle baselines
- Detects recurring coaching issues
- Identifies objection handling weaknesses
- Tracks coaching target progress
- Deduplicates nudges via fingerprint hashing

Also provides CRUD operations for the nudge API:
- List nudges with read/unread status per user
- Mark nudges as read/dismissed
- Get unread count for notification badge
"""
import hashlib
from collections import Counter
from datetime import datetime, timedelta, timezone, date
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, case, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.coaching import (
    CoachingSessionORM,
    CoachingIssueORM,
    CoachingStrengthORM,
    CallObjectionDetailORM,
)
from app.infrastructure.database.models.smart_nudge import (
    SmartNudgeORM,
    SmartNudgeReadORM,
)

logger = get_logger(__name__)

# Thresholds
IMPROVEMENT_THRESHOLD = 10.0    # +10% = positive nudge
DECLINE_THRESHOLD = -10.0       # -10% = warning nudge
CRITICAL_DECLINE_THRESHOLD = -20.0  # -20% = critical nudge
RECURRING_ISSUE_MIN_COUNT = 3   # Issue appears 3+ times
OBJECTION_WEAKNESS_RATE = 0.30  # Below 30% overcome rate
OBJECTION_MIN_COUNT = 3         # At least 3 objections in category
NUDGE_EXPIRY_DAYS = 7           # Nudges expire after 7 days
DEDUP_WINDOW_DAYS = 7           # Don't repeat same nudge within 7 days

# Metrics we track from call_analyses
METRIC_LABELS = {
    "compliance_score": "SOP compliance",
    "booking_rate": "booking rate",
    "qualification_accuracy": "lead qualification accuracy",
    "sentiment": "conversation quality",
    "objection_handling": "objection handling",
    "budget_qualification": "budget qualification",
    "timeline_qualification": "timeline qualification",
}


class SmartNudgeService:
    """Generates and manages smart coaching nudges."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # Main Evaluation Entry Point (called by cron)
    # =========================================================================

    async def evaluate_all_companies(self) -> int:
        """
        Evaluate all companies with active coaching sessions and generate nudges.
        Returns total nudges generated.
        """
        # Get distinct company_ids that have active coaching sessions
        result = await self.session.execute(
            select(CoachingSessionORM.company_id).where(
                CoachingSessionORM.status == "in_progress"
            ).distinct()
        )
        company_ids = [row[0] for row in result]

        total_nudges = 0
        for company_id in company_ids:
            try:
                count = await self._evaluate_company(company_id)
                total_nudges += count
            except Exception as e:
                logger.error(f"Nudge evaluation failed for company {company_id}: {e}")
                continue

        await self.session.commit()
        logger.info(f"Generated {total_nudges} nudges across {len(company_ids)} companies")
        return total_nudges

    async def _evaluate_company(self, company_id: UUID) -> int:
        """Evaluate all reps with active sessions in a company."""
        # Get all active coaching sessions
        result = await self.session.execute(
            select(CoachingSessionORM).where(
                CoachingSessionORM.company_id == company_id,
                CoachingSessionORM.status == "in_progress",
            )
        )
        sessions = result.scalars().all()

        nudges_generated = 0
        for cs in sessions:
            try:
                nudges = await self._evaluate_rep(cs)
                nudges_generated += len(nudges)
            except Exception as e:
                logger.error(f"Nudge evaluation failed for rep {cs.rep_user_id}: {e}")
                continue

        return nudges_generated

    async def _evaluate_rep(self, cs: CoachingSessionORM) -> List[SmartNudgeORM]:
        """Run all nudge detection rules for a rep in an active coaching session."""
        now = datetime.now(timezone.utc)
        nudges: List[SmartNudgeORM] = []

        rep = await self.session.get(UserORM, cs.rep_user_id)
        rep_name = (
            f"{rep.first_name or ''} {rep.last_name or ''}".strip()
            if rep else "Unknown"
        )

        baseline = cs.baseline_scores or {}

        # Rule 1 & 2: Metric improvement/decline vs baseline
        current_metrics = await self._compute_current_metrics(cs)
        for metric, current in current_metrics.items():
            base_val = baseline.get(metric)
            if base_val is None or base_val == 0:
                continue

            change_pct = (current - base_val) / base_val * 100
            label = METRIC_LABELS.get(metric, metric)

            if change_pct <= CRITICAL_DECLINE_THRESHOLD:
                nudges.append(self._build_nudge(
                    cs=cs, rep_name=rep_name,
                    nudge_type="critical_decline", priority="critical",
                    title=f"{rep_name}'s {label} dropped {abs(change_pct):.0f}%",
                    message=(
                        f"{rep_name}'s {label} dropped by {abs(change_pct):.0f}% "
                        f"compared to cycle {cs.cycle_number} baseline "
                        f"({base_val:.2f} → {current:.2f}). Immediate attention needed."
                    ),
                    metric_name=metric, previous_value=base_val,
                    current_value=current, change_pct=change_pct,
                    window="vs cycle baseline", now=now,
                ))
            elif change_pct <= DECLINE_THRESHOLD:
                nudges.append(self._build_nudge(
                    cs=cs, rep_name=rep_name,
                    nudge_type="metric_decline", priority="high",
                    title=f"{rep_name}'s {label} dropped {abs(change_pct):.0f}%",
                    message=(
                        f"{rep_name}'s {label} dropped by {abs(change_pct):.0f}% "
                        f"compared to cycle {cs.cycle_number} baseline "
                        f"({base_val:.2f} → {current:.2f})."
                    ),
                    metric_name=metric, previous_value=base_val,
                    current_value=current, change_pct=change_pct,
                    window="vs cycle baseline", now=now,
                ))
            elif change_pct >= IMPROVEMENT_THRESHOLD:
                nudges.append(self._build_nudge(
                    cs=cs, rep_name=rep_name,
                    nudge_type="metric_improvement", priority="positive",
                    title=f"{rep_name}'s {label} improved {change_pct:.0f}%",
                    message=(
                        f"{rep_name}'s {label} improved by {change_pct:.0f}% "
                        f"compared to cycle {cs.cycle_number} baseline "
                        f"({base_val:.2f} → {current:.2f})."
                    ),
                    metric_name=metric, previous_value=base_val,
                    current_value=current, change_pct=change_pct,
                    window="vs cycle baseline", now=now,
                ))

        # Rule 3: Recurring coaching issues
        recurring_nudges = await self._check_recurring_issues(cs, rep_name, now)
        nudges.extend(recurring_nudges)

        # Rule 4: Objection weakness
        objection_nudges = await self._check_objection_weakness(cs, rep_name, now)
        nudges.extend(objection_nudges)

        # Rule 5: Coaching target tracking
        target_nudges = await self._check_targets(cs, current_metrics, rep_name, now)
        nudges.extend(target_nudges)

        # Deduplicate against existing nudges
        final_nudges = await self._deduplicate(nudges)

        for nudge in final_nudges:
            self.session.add(nudge)

        return final_nudges

    # =========================================================================
    # Metric Computation
    # =========================================================================

    async def _compute_current_metrics(
        self, cs: CoachingSessionORM
    ) -> Dict[str, float]:
        """Compute current metrics for a rep during the active coaching cycle."""
        start_dt = cs.coached_at
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

        result = await self.session.execute(
            select(CallAnalysisORM)
            .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id == cs.rep_user_id,
                CallORM.company_id == cs.company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at <= now,
                CallAnalysisORM.status == "completed",
            )
        )
        analyses = result.scalars().all()

        if not analyses:
            return {}

        from collections import defaultdict
        scores: Dict[str, List[float]] = defaultdict(list)

        for a in analyses:
            if a.sop_compliance_score is not None:
                scores["compliance_score"].append(a.sop_compliance_score)
            if a.booking_status:
                scores["booking_rate"].append(
                    1.0 if a.booking_status.lower() == "booked" else 0.0
                )
            if a.sentiment_score is not None:
                scores["sentiment"].append(a.sentiment_score)
            if a.qualification_overall_score is not None:
                scores["qualification_accuracy"].append(a.qualification_overall_score)
            if a.bant_budget_score is not None:
                scores["budget_qualification"].append(a.bant_budget_score)
            if a.bant_timeline_score is not None:
                scores["timeline_qualification"].append(a.bant_timeline_score)

        # Objection handling
        obj_result = await self.session.execute(
            select(
                func.count(CallObjectionDetailORM.id).label("total"),
                func.count(
                    case((CallObjectionDetailORM.overcome == True, 1))
                ).label("overcome"),
            ).where(
                CallObjectionDetailORM.user_id == cs.rep_user_id,
                CallObjectionDetailORM.company_id == cs.company_id,
                CallObjectionDetailORM.created_at >= start_dt,
                CallObjectionDetailORM.created_at <= now,
            )
        )
        obj_row = obj_result.one_or_none()
        if obj_row and obj_row.total > 0:
            scores["objection_handling"].append(obj_row.overcome / obj_row.total)

        metrics = {}
        for metric, values in scores.items():
            if values:
                metrics[metric] = round(sum(values) / len(values), 3)

        return metrics

    # =========================================================================
    # Rule: Recurring Issues
    # =========================================================================

    async def _check_recurring_issues(
        self, cs: CoachingSessionORM, rep_name: str, now: datetime
    ) -> List[SmartNudgeORM]:
        """Check for coaching issues that recur frequently within the cycle."""
        start_dt = cs.coached_at
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        result = await self.session.execute(
            select(CoachingIssueORM).where(
                CoachingIssueORM.user_id == cs.rep_user_id,
                CoachingIssueORM.company_id == cs.company_id,
                CoachingIssueORM.created_at >= start_dt,
                CoachingIssueORM.created_at <= now,
            )
        )
        issues = result.scalars().all()

        issue_counts = Counter(i.issue.strip().lower() for i in issues)
        # Also keep the original text for display
        issue_originals = {}
        issue_how_to_fix = {}
        for i in issues:
            key = i.issue.strip().lower()
            if key not in issue_originals:
                issue_originals[key] = i.issue
                issue_how_to_fix[key] = i.how_to_fix

        nudges = []
        for issue_key, count in issue_counts.items():
            if count >= RECURRING_ISSUE_MIN_COUNT:
                original = issue_originals.get(issue_key, issue_key)
                fix = issue_how_to_fix.get(issue_key, "")
                nudges.append(self._build_nudge(
                    cs=cs, rep_name=rep_name,
                    nudge_type="recurring_issue", priority="high",
                    title=f"Recurring: {original[:80]}",
                    message=(
                        f"{rep_name} has repeated '{original}' in {count} calls "
                        f"during cycle {cs.cycle_number}."
                        + (f" Suggestion: {fix}" if fix else "")
                    ),
                    metric_name=None, previous_value=None,
                    current_value=None, change_pct=None,
                    window=f"cycle {cs.cycle_number}", now=now,
                    extra_fingerprint=issue_key,
                ))

        return nudges

    # =========================================================================
    # Rule: Objection Weakness
    # =========================================================================

    async def _check_objection_weakness(
        self, cs: CoachingSessionORM, rep_name: str, now: datetime
    ) -> List[SmartNudgeORM]:
        """Check for objection categories where rep overcome rate is weak."""
        start_dt = cs.coached_at
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        # Rep's objection stats
        rep_result = await self.session.execute(
            select(
                CallObjectionDetailORM.category_text,
                func.count(CallObjectionDetailORM.id).label("total"),
                func.count(
                    case((CallObjectionDetailORM.overcome == True, 1))
                ).label("overcome"),
            ).where(
                CallObjectionDetailORM.user_id == cs.rep_user_id,
                CallObjectionDetailORM.company_id == cs.company_id,
                CallObjectionDetailORM.created_at >= start_dt,
                CallObjectionDetailORM.created_at <= now,
            ).group_by(CallObjectionDetailORM.category_text)
        )

        # Team average for comparison
        team_result = await self.session.execute(
            select(
                CallObjectionDetailORM.category_text,
                func.count(CallObjectionDetailORM.id).label("total"),
                func.count(
                    case((CallObjectionDetailORM.overcome == True, 1))
                ).label("overcome"),
            ).where(
                CallObjectionDetailORM.company_id == cs.company_id,
                CallObjectionDetailORM.created_at >= start_dt,
                CallObjectionDetailORM.created_at <= now,
            ).group_by(CallObjectionDetailORM.category_text)
        )
        team_rates = {}
        for row in team_result:
            if row.total > 0:
                team_rates[row.category_text] = row.overcome / row.total

        nudges = []
        for row in rep_result:
            if row.total < OBJECTION_MIN_COUNT:
                continue
            rep_rate = row.overcome / row.total if row.total > 0 else 0
            team_rate = team_rates.get(row.category_text, 0.5)

            if rep_rate < OBJECTION_WEAKNESS_RATE and rep_rate < team_rate - 0.15:
                nudges.append(self._build_nudge(
                    cs=cs, rep_name=rep_name,
                    nudge_type="objection_weakness", priority="high",
                    title=f"{rep_name}: weak on '{row.category_text}' objections",
                    message=(
                        f"{rep_name} overcomes '{row.category_text}' objections only "
                        f"{rep_rate * 100:.0f}% of the time (team avg: {team_rate * 100:.0f}%). "
                        f"Practice value-based responses for this objection type."
                    ),
                    metric_name=f"objection:{row.category_text}",
                    previous_value=team_rate, current_value=rep_rate,
                    change_pct=None,
                    window=f"cycle {cs.cycle_number}", now=now,
                ))

        return nudges

    # =========================================================================
    # Rule: Target Tracking
    # =========================================================================

    async def _check_targets(
        self, cs: CoachingSessionORM, current_metrics: Dict[str, float],
        rep_name: str, now: datetime,
    ) -> List[SmartNudgeORM]:
        """Check if coaching targets have been met mid-cycle."""
        if not cs.targets:
            return []

        nudges = []
        for metric, target in cs.targets.items():
            current = current_metrics.get(metric)
            if current is None:
                continue

            if current >= target:
                nudges.append(self._build_nudge(
                    cs=cs, rep_name=rep_name,
                    nudge_type="coaching_target_met", priority="positive",
                    title=f"{rep_name} met {METRIC_LABELS.get(metric, metric)} target!",
                    message=(
                        f"{rep_name}'s {METRIC_LABELS.get(metric, metric)} reached "
                        f"{current:.2f}, meeting the target of {target:.2f} "
                        f"set in coaching cycle {cs.cycle_number}."
                    ),
                    metric_name=metric, previous_value=target,
                    current_value=current, change_pct=None,
                    window=f"cycle {cs.cycle_number}", now=now,
                    extra_fingerprint=f"target_met_{metric}",
                ))

        return nudges

    # =========================================================================
    # Nudge Builder & Dedup
    # =========================================================================

    def _build_nudge(
        self,
        cs: CoachingSessionORM,
        rep_name: str,
        nudge_type: str,
        priority: str,
        title: str,
        message: str,
        metric_name: Optional[str],
        previous_value: Optional[float],
        current_value: Optional[float],
        change_pct: Optional[float],
        window: str,
        now: datetime,
        extra_fingerprint: str = "",
    ) -> SmartNudgeORM:
        """Build a SmartNudgeORM instance with computed fingerprint."""
        fp_input = f"{cs.rep_user_id}:{nudge_type}:{metric_name or ''}:{cs.cycle_number}:{extra_fingerprint}"
        fingerprint = hashlib.sha256(fp_input.encode()).hexdigest()

        return SmartNudgeORM(
            company_id=cs.company_id,
            rep_user_id=cs.rep_user_id,
            rep_name=rep_name,
            nudge_type=nudge_type,
            priority=priority,
            title=title[:255],
            message=message,
            metric_name=metric_name,
            previous_value=previous_value,
            current_value=current_value,
            change_pct=change_pct,
            window_description=window,
            source_session_id=cs.id,
            fingerprint=fingerprint,
            expires_at=now + timedelta(days=NUDGE_EXPIRY_DAYS),
        )

    async def _deduplicate(self, nudges: List[SmartNudgeORM]) -> List[SmartNudgeORM]:
        """Remove nudges that already exist within the dedup window."""
        if not nudges:
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)
        fingerprints = [n.fingerprint for n in nudges]

        result = await self.session.execute(
            select(SmartNudgeORM.fingerprint).where(
                SmartNudgeORM.fingerprint.in_(fingerprints),
                SmartNudgeORM.created_at >= cutoff,
            )
        )
        existing = {row[0] for row in result}

        deduped = []
        seen = set()
        for nudge in nudges:
            if nudge.fingerprint not in existing and nudge.fingerprint not in seen:
                deduped.append(nudge)
                seen.add(nudge.fingerprint)

        if len(nudges) != len(deduped):
            logger.info(
                f"Deduplication: {len(nudges)} candidates → {len(deduped)} new nudges"
            )

        return deduped

    # =========================================================================
    # CRUD: List Nudges
    # =========================================================================

    async def list_nudges(
        self,
        company_id: UUID,
        current_user_id: UUID,
        status_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        rep_user_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List nudges for a company with per-user read status.

        Args:
            status_filter: 'unread', 'read', 'dismissed', or None (all)
            priority_filter: 'critical', 'high', 'medium', 'low', 'positive', or None
        """
        now = datetime.now(timezone.utc)

        # Base query with LEFT JOIN to get read status
        base_filters = [
            SmartNudgeORM.company_id == company_id,
            (SmartNudgeORM.expires_at.is_(None)) | (SmartNudgeORM.expires_at > now),
        ]
        if priority_filter:
            base_filters.append(SmartNudgeORM.priority == priority_filter)
        if rep_user_id:
            base_filters.append(SmartNudgeORM.rep_user_id == rep_user_id)

        # Count total matching
        total_q = select(func.count(SmartNudgeORM.id)).where(*base_filters)
        total_result = await self.session.execute(total_q)
        total = total_result.scalar() or 0

        # Count unread
        unread_q = (
            select(func.count(SmartNudgeORM.id))
            .outerjoin(
                SmartNudgeReadORM,
                and_(
                    SmartNudgeReadORM.nudge_id == SmartNudgeORM.id,
                    SmartNudgeReadORM.user_id == current_user_id,
                ),
            )
            .where(*base_filters, SmartNudgeReadORM.id.is_(None))
        )
        unread_result = await self.session.execute(unread_q)
        unread_count = unread_result.scalar() or 0

        # Main query
        q = (
            select(SmartNudgeORM, SmartNudgeReadORM)
            .outerjoin(
                SmartNudgeReadORM,
                and_(
                    SmartNudgeReadORM.nudge_id == SmartNudgeORM.id,
                    SmartNudgeReadORM.user_id == current_user_id,
                ),
            )
            .where(*base_filters)
        )

        # Apply status filter
        if status_filter == "unread":
            q = q.where(SmartNudgeReadORM.id.is_(None))
        elif status_filter == "read":
            q = q.where(
                SmartNudgeReadORM.id.isnot(None),
                SmartNudgeReadORM.status == "read",
            )
        elif status_filter == "dismissed":
            q = q.where(
                SmartNudgeReadORM.id.isnot(None),
                SmartNudgeReadORM.status == "dismissed",
            )

        q = q.order_by(SmartNudgeORM.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(q)
        rows = result.all()

        nudges = []
        for nudge, read_record in rows:
            read_status = "unread"
            read_at = None
            if read_record:
                read_status = read_record.status
                read_at = read_record.read_at

            nudges.append({
                "id": nudge.id,
                "company_id": nudge.company_id,
                "rep_user_id": nudge.rep_user_id,
                "rep_name": nudge.rep_name,
                "nudge_type": nudge.nudge_type,
                "priority": nudge.priority,
                "title": nudge.title,
                "message": nudge.message,
                "metric_name": nudge.metric_name,
                "previous_value": nudge.previous_value,
                "current_value": nudge.current_value,
                "change_pct": nudge.change_pct,
                "window_description": nudge.window_description,
                "source_session_id": nudge.source_session_id,
                "extra_data": nudge.extra_data,
                "created_at": nudge.created_at,
                "expires_at": nudge.expires_at,
                "read_status": read_status,
                "read_at": read_at,
            })

        return {
            "total": total,
            "unread_count": unread_count,
            "limit": limit,
            "offset": offset,
            "nudges": nudges,
        }

    # =========================================================================
    # CRUD: Unread Count
    # =========================================================================

    async def get_unread_count(
        self, company_id: UUID, current_user_id: UUID
    ) -> int:
        """Get count of unread nudges for the current user."""
        now = datetime.now(timezone.utc)

        result = await self.session.execute(
            select(func.count(SmartNudgeORM.id))
            .outerjoin(
                SmartNudgeReadORM,
                and_(
                    SmartNudgeReadORM.nudge_id == SmartNudgeORM.id,
                    SmartNudgeReadORM.user_id == current_user_id,
                ),
            )
            .where(
                SmartNudgeORM.company_id == company_id,
                (SmartNudgeORM.expires_at.is_(None)) | (SmartNudgeORM.expires_at > now),
                SmartNudgeReadORM.id.is_(None),
            )
        )
        return result.scalar() or 0

    # =========================================================================
    # CRUD: Mark Read / Dismissed
    # =========================================================================

    async def mark_read(self, nudge_id: UUID, user_id: UUID) -> SmartNudgeReadORM:
        """Mark a nudge as read for a specific user."""
        # Check if already exists
        result = await self.session.execute(
            select(SmartNudgeReadORM).where(
                SmartNudgeReadORM.nudge_id == nudge_id,
                SmartNudgeReadORM.user_id == user_id,
            )
        )
        existing = result.scalars().first()

        if existing:
            existing.status = "read"
            existing.read_at = datetime.now(timezone.utc)
            await self.session.commit()
            return existing

        read_record = SmartNudgeReadORM(
            nudge_id=nudge_id,
            user_id=user_id,
            status="read",
        )
        self.session.add(read_record)
        await self.session.commit()
        return read_record

    async def mark_dismissed(self, nudge_id: UUID, user_id: UUID) -> SmartNudgeReadORM:
        """Mark a nudge as dismissed for a specific user."""
        result = await self.session.execute(
            select(SmartNudgeReadORM).where(
                SmartNudgeReadORM.nudge_id == nudge_id,
                SmartNudgeReadORM.user_id == user_id,
            )
        )
        existing = result.scalars().first()

        now = datetime.now(timezone.utc)
        if existing:
            existing.status = "dismissed"
            existing.dismissed_at = now
            await self.session.commit()
            return existing

        read_record = SmartNudgeReadORM(
            nudge_id=nudge_id,
            user_id=user_id,
            status="dismissed",
            dismissed_at=now,
        )
        self.session.add(read_record)
        await self.session.commit()
        return read_record

    async def mark_all_read(self, company_id: UUID, user_id: UUID) -> int:
        """Mark all unread nudges as read for a user. Returns count marked."""
        now = datetime.now(timezone.utc)

        # Get all unread nudge IDs for this user
        result = await self.session.execute(
            select(SmartNudgeORM.id)
            .outerjoin(
                SmartNudgeReadORM,
                and_(
                    SmartNudgeReadORM.nudge_id == SmartNudgeORM.id,
                    SmartNudgeReadORM.user_id == user_id,
                ),
            )
            .where(
                SmartNudgeORM.company_id == company_id,
                (SmartNudgeORM.expires_at.is_(None)) | (SmartNudgeORM.expires_at > now),
                SmartNudgeReadORM.id.is_(None),
            )
        )
        unread_ids = [row[0] for row in result]

        for nudge_id in unread_ids:
            self.session.add(SmartNudgeReadORM(
                nudge_id=nudge_id,
                user_id=user_id,
                status="read",
            ))

        await self.session.commit()
        return len(unread_ids)

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup_expired(self) -> int:
        """Delete expired nudges. Returns count deleted."""
        now = datetime.now(timezone.utc)

        # Count first
        count_result = await self.session.execute(
            select(func.count(SmartNudgeORM.id)).where(
                SmartNudgeORM.expires_at.isnot(None),
                SmartNudgeORM.expires_at < now,
            )
        )
        count = count_result.scalar() or 0

        if count > 0:
            # Delete via raw SQL for efficiency (CASCADE handles reads)
            await self.session.execute(
                text(
                    "DELETE FROM smart_nudges WHERE expires_at IS NOT NULL AND expires_at < :now"
                ),
                {"now": now},
            )
            await self.session.commit()
            logger.info(f"Cleaned up {count} expired nudges")

        return count
