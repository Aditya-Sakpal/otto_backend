"""
Coaching Cycle Service.

Manages 7-day auto-restarting coaching cycles:
- Completes expired cycles and computes impact scores
- Auto-creates next cycle with updated baseline
- Generates cycle-end nudges
- Supports manual stop to halt auto-cycling
"""
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.coaching import (
    CoachingSessionORM,
    CoachingIssueORM,
    CallObjectionDetailORM,
)
from app.infrastructure.database.models.smart_nudge import SmartNudgeORM
from app.infrastructure.integrations.shoonya import get_shoonya_client

logger = get_logger(__name__)

# Default coaching cycle duration
CYCLE_DAYS = 7


class CoachingCycleService:
    """Manages 7-day auto-cycling coaching sessions."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.shoonya = get_shoonya_client()

    # =========================================================================
    # Main Cron Entry Point
    # =========================================================================

    async def process_expired_cycles(self) -> int:
        """
        Find all in_progress coaching sessions whose 7-day window has ended,
        complete them, compute impact, and auto-create the next cycle.

        Returns the number of cycles processed.
        """
        now = datetime.now(timezone.utc)

        result = await self.session.execute(
            select(CoachingSessionORM).where(
                CoachingSessionORM.status == "in_progress",
                CoachingSessionORM.follow_up_end_date <= now,
            )
        )
        expired_sessions = result.scalars().all()

        if not expired_sessions:
            return 0

        processed = 0
        for cs in expired_sessions:
            try:
                await self._complete_and_restart_cycle(cs, now)
                processed += 1
            except Exception as e:
                logger.error(
                    f"Failed to process cycle for session {cs.id}: {e}",
                    session_id=str(cs.id),
                )
                continue

        await self.session.commit()
        logger.info(f"Processed {processed} expired coaching cycles")
        return processed

    # =========================================================================
    # Cycle Completion & Restart
    # =========================================================================

    async def _complete_and_restart_cycle(
        self, cs: CoachingSessionORM, now: datetime
    ):
        """Complete a cycle, measure impact, create next cycle, generate nudge."""
        # 1. Compute impact for this cycle
        impact = await self._compute_cycle_impact(cs)

        # 2. Update current cycle as completed
        cs.impact_scores = impact["scores"]
        cs.overall_improved = impact["overall_improved"]
        cs.improvement_pct = impact["improvement_pct"]
        cs.targets_met = impact["targets_met"]
        cs.status = "completed"
        cs.updated_at = now

        # 3. Generate cycle summary nudge
        await self._generate_cycle_nudge(cs, impact, now)

        # 4. Get rep and coach info for Shunya sync
        rep = await self.session.get(UserORM, cs.rep_user_id)
        coach = await self.session.get(UserORM, cs.coach_user_id)

        # 5. Try to sync with Shunya (non-blocking)
        try:
            if self.shoonya.is_available():
                await self.shoonya.update_shunya_coaching_session_status(
                    session_id=str(cs.id),
                    status="completed",
                    measure_impact=True,
                    notes=f"Auto-completed cycle {cs.cycle_number}",
                )
        except Exception as e:
            logger.warning(f"Failed to sync cycle completion with Shunya: {e}")

        # 6. Create next cycle
        original_id = cs.parent_session_id or cs.id
        next_cycle = CoachingSessionORM(
            company_id=cs.company_id,
            rep_user_id=cs.rep_user_id,
            coach_user_id=cs.coach_user_id,
            focus_areas=cs.focus_areas,
            targets=cs.targets,
            baseline_scores=impact["scores"] if impact["scores"] else cs.baseline_scores,
            status="in_progress",
            follow_up_days=CYCLE_DAYS,
            follow_up_end_date=now + timedelta(days=CYCLE_DAYS),
            notes=f"Auto-created cycle {cs.cycle_number + 1}",
            coached_at=now,
            cycle_number=cs.cycle_number + 1,
            parent_session_id=original_id,
            auto_created=True,
        )
        self.session.add(next_cycle)

        # 7. Try to create on Shunya too (non-blocking)
        try:
            if self.shoonya.is_available() and rep and coach:
                rep_name = f"{rep.first_name or ''} {rep.last_name or ''}".strip()
                coach_name = f"{coach.first_name or ''} {coach.last_name or ''}".strip()
                await self.shoonya.create_shunya_coaching_session(
                    company_id=str(cs.company_id),
                    rep_id=str(cs.rep_user_id),
                    rep_name=rep_name,
                    coach_id=str(cs.coach_user_id),
                    coach_name=coach_name,
                    focus_areas=cs.focus_areas or [],
                    targets=cs.targets,
                    follow_up_days=CYCLE_DAYS,
                    notes=f"Auto-created cycle {cs.cycle_number + 1}",
                )
        except Exception as e:
            logger.warning(f"Failed to create next cycle on Shunya: {e}")

        logger.info(
            f"Completed cycle {cs.cycle_number} for rep {cs.rep_user_id}, "
            f"created cycle {cs.cycle_number + 1}"
        )

    # =========================================================================
    # Impact Computation
    # =========================================================================

    async def _compute_cycle_impact(self, cs: CoachingSessionORM) -> Dict[str, Any]:
        """
        Compute impact scores for a coaching cycle by averaging call_analyses
        metrics during the cycle window [coached_at, follow_up_end_date].
        """
        start_dt = cs.coached_at
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        end_dt = cs.follow_up_end_date
        if end_dt and end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        # Query call analyses for this rep during the cycle
        result = await self.session.execute(
            select(CallAnalysisORM)
            .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id == cs.rep_user_id,
                CallORM.company_id == cs.company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt,
                CallAnalysisORM.status == "completed",
            )
        )
        analyses = result.scalars().all()

        if not analyses:
            return {
                "scores": cs.baseline_scores or {},
                "overall_improved": None,
                "improvement_pct": None,
                "targets_met": None,
                "calls_analyzed": 0,
            }

        # Compute metric averages
        scores: Dict[str, List[float]] = defaultdict(list)
        for a in analyses:
            if a.sop_compliance_score is not None:
                scores["compliance_score"].append(a.sop_compliance_score)
            if a.booking_status:
                scores["booking_rate"].append(
                    1.0 if a.booking_status.lower() == "booked" else 0.0
                )
            if a.sentiment_score is not None:
                scores["rapport_score"].append(a.sentiment_score)
            if a.qualification_overall_score is not None:
                scores["qualification_accuracy"].append(a.qualification_overall_score)
            if a.bant_budget_score is not None:
                scores["budget_qualification"].append(a.bant_budget_score)
            if a.bant_timeline_score is not None:
                scores["timeline_qualification"].append(a.bant_timeline_score)

        # Also compute objection handling rate
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
                CallObjectionDetailORM.created_at <= end_dt,
            )
        )
        obj_row = obj_result.one_or_none()
        if obj_row and obj_row.total > 0:
            scores["objection_handling"].append(obj_row.overcome / obj_row.total)

        avg_scores = {}
        for metric, values in scores.items():
            if values:
                avg_scores[metric] = round(sum(values) / len(values), 3)

        # Compare against baseline
        baseline = cs.baseline_scores or {}
        improvements = {}
        improved_count = 0
        total_compared = 0

        for metric, current in avg_scores.items():
            base_val = baseline.get(metric)
            if base_val is not None and base_val > 0:
                change = (current - base_val) / base_val * 100
                improvements[metric] = round(change, 1)
                if change > 0:
                    improved_count += 1
                total_compared += 1

        overall_improved = improved_count > total_compared / 2 if total_compared > 0 else None
        improvement_pct = (
            round(sum(improvements.values()) / len(improvements), 1)
            if improvements
            else None
        )

        # Check targets
        targets_met = None
        if cs.targets:
            targets_met = {}
            for metric, target in cs.targets.items():
                current = avg_scores.get(metric)
                targets_met[metric] = current >= target if current is not None else False

        return {
            "scores": avg_scores,
            "overall_improved": overall_improved,
            "improvement_pct": improvement_pct,
            "targets_met": targets_met,
            "calls_analyzed": len(analyses),
        }

    # =========================================================================
    # Cycle Summary Nudge
    # =========================================================================

    async def _generate_cycle_nudge(
        self, cs: CoachingSessionORM, impact: Dict[str, Any], now: datetime
    ):
        """Generate a cycle_summary nudge after completing a cycle."""
        rep = await self.session.get(UserORM, cs.rep_user_id)
        rep_name = (
            f"{rep.first_name or ''} {rep.last_name or ''}".strip()
            if rep
            else "Unknown"
        )

        calls_analyzed = impact.get("calls_analyzed", 0)
        overall_improved = impact.get("overall_improved")
        improvement_pct = impact.get("improvement_pct")

        if overall_improved and improvement_pct is not None:
            title = f"Cycle {cs.cycle_number} Complete: {rep_name} improved {improvement_pct:.0f}%"
            message = (
                f"Coaching cycle {cs.cycle_number} completed for {rep_name}. "
                f"Overall improvement of {improvement_pct:.0f}% across {calls_analyzed} calls. "
                f"New cycle {cs.cycle_number + 1} started with updated baseline."
            )
            priority = "positive"
        elif calls_analyzed == 0:
            title = f"Cycle {cs.cycle_number} Complete: No calls for {rep_name}"
            message = (
                f"Coaching cycle {cs.cycle_number} completed for {rep_name} "
                f"but no calls were recorded during the 7-day period. "
                f"New cycle {cs.cycle_number + 1} started with same baseline."
            )
            priority = "medium"
        else:
            pct_str = f"{improvement_pct:.0f}%" if improvement_pct is not None else "N/A"
            title = f"Cycle {cs.cycle_number} Complete: {rep_name} ({pct_str})"
            message = (
                f"Coaching cycle {cs.cycle_number} completed for {rep_name}. "
                f"{calls_analyzed} calls analyzed. "
                f"New cycle {cs.cycle_number + 1} started."
            )
            priority = "medium"

        fingerprint = hashlib.sha256(
            f"{cs.rep_user_id}:cycle_summary:{cs.cycle_number}".encode()
        ).hexdigest()

        nudge = SmartNudgeORM(
            company_id=cs.company_id,
            rep_user_id=cs.rep_user_id,
            rep_name=rep_name,
            nudge_type="cycle_summary",
            priority=priority,
            title=title[:255],
            message=message,
            metric_name=None,
            previous_value=None,
            current_value=None,
            change_pct=impact.get("improvement_pct"),
            window_description=f"cycle {cs.cycle_number}",
            source_session_id=cs.id,
            extra_data={
                "cycle_number": cs.cycle_number,
                "calls_analyzed": calls_analyzed,
                "scores": impact.get("scores"),
                "targets_met": impact.get("targets_met"),
            },
            fingerprint=fingerprint,
            expires_at=now + timedelta(days=7),
        )
        self.session.add(nudge)

    # =========================================================================
    # Manual Stop
    # =========================================================================

    async def stop_coaching(
        self, session_id: UUID, notes: Optional[str] = None
    ) -> CoachingSessionORM:
        """
        Stop auto-cycling for a coaching session.
        Sets the current active cycle to 'stopped' status.
        """
        # Find the active cycle in this chain
        cs = await self.session.get(CoachingSessionORM, session_id)
        if not cs:
            raise ValueError(f"Session {session_id} not found")

        # If this is a parent, find the latest active child
        if cs.status != "in_progress":
            result = await self.session.execute(
                select(CoachingSessionORM).where(
                    CoachingSessionORM.status == "in_progress",
                    CoachingSessionORM.parent_session_id == session_id,
                ).order_by(CoachingSessionORM.cycle_number.desc()).limit(1)
            )
            active = result.scalars().first()
            if active:
                cs = active

        if cs.status != "in_progress":
            raise ValueError(f"No active cycle found for session {session_id}")

        cs.status = "stopped"
        cs.updated_at = datetime.now(timezone.utc)
        if notes:
            cs.notes = (cs.notes or "") + f"\nStopped: {notes}"

        await self.session.commit()
        await self.session.refresh(cs)

        logger.info(f"Stopped coaching for session {session_id}, cycle {cs.cycle_number}")
        return cs

    # =========================================================================
    # Session History
    # =========================================================================

    async def get_session_history(self, session_id: UUID) -> Dict[str, Any]:
        """
        Get all cycles in a coaching session chain.
        """
        # Get the session to determine if it's a parent or child
        cs = await self.session.get(CoachingSessionORM, session_id)
        if not cs:
            raise ValueError(f"Session {session_id} not found")

        original_id = cs.parent_session_id or cs.id

        # Get all cycles in this chain
        result = await self.session.execute(
            select(CoachingSessionORM).where(
                (CoachingSessionORM.id == original_id)
                | (CoachingSessionORM.parent_session_id == original_id)
            ).order_by(CoachingSessionORM.cycle_number.desc())
        )
        all_cycles = result.scalars().all()

        active_cycle = None
        completed_cycles = []

        for cycle in all_cycles:
            if cycle.status == "in_progress":
                active_cycle = cycle
            else:
                completed_cycles.append(cycle)

        return {
            "original_session_id": original_id,
            "rep_user_id": cs.rep_user_id,
            "total_cycles": len(all_cycles),
            "active_cycle": active_cycle,
            "completed_cycles": completed_cycles,
        }
