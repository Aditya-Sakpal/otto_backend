"""
Coaching service.

Provides business logic for the coaching dashboard:
- Team overview with compliance/booking aggregation
- Issues and strengths from dedicated tables
- Progression and peer benchmark via Shunya API
- Coaching session impact tracking
- Objection struggle areas
- Smart nudge generation
"""
import asyncio
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.coaching import (
    CoachingIssueORM,
    CoachingStrengthORM,
    CallObjectionDetailORM,
    CoachingSessionORM,
)
from app.infrastructure.integrations.shoonya import get_shoonya_client
from app.domain.schemas.coaching import (
    TeamMemberSummary,
    TeamStats,
    TeamOverviewResponse,
    CoachingIssueResponse,
    RepIssuesResponse,
    CoachingStrengthResponse,
    RepStrengthsResponse,
    RepProgressionResponse,
    PeerBenchmarkMetric,
    RepPeerBenchmarkResponse,
    CoachingSessionSummary,
    RepImpactResponse,
    ObjectionCategory,
    RepObjectionsResponse,
    SmartNudge,
    RepSmartNudgesResponse,
    CoachingSessionResponse,
    CoachingSessionListResponse,
    CoachingDashboardResponse,
    TeamDashboardResponse,
    IndividualDashboardResponse,
)

logger = get_logger(__name__)


class CoachingService:
    """Service for coaching dashboard data."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.shoonya = get_shoonya_client()

    # =========================================================================
    # Combined Dashboard
    # =========================================================================

    async def get_dashboard(
        self,
        user_id: UUID,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        weeks: int = 8,
        days: int = 30,
        role_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> CoachingDashboardResponse:
        """Fetch all coaching dashboard data.

        DB-dependent sections run sequentially (AsyncSession is not safe for
        concurrent use), while external Shunya API calls run in parallel.
        """

        async def _safe(coro, label: str):
            try:
                return await coro
            except Exception as e:
                logger.warning(f"Dashboard section '{label}' failed: {e}")
                return None

        # 1. Run DB-dependent sections sequentially (same session)
        team = await _safe(self.get_team_overview(company_id, role_filter, search, start_date, end_date), "team")
        issues = await _safe(self.get_rep_issues(user_id, company_id, start_date, end_date), "issues")
        strengths = await _safe(self.get_rep_strengths(user_id, company_id, start_date, end_date), "strengths")
        impact = await _safe(self.get_rep_impact(user_id, company_id), "impact")
        objections = await _safe(self.get_rep_objections(user_id, company_id, start_date, end_date), "objections")
        nudges = await _safe(self.get_rep_nudges(user_id, company_id, start_date, end_date), "nudges")

        # 2. Run external Shunya API calls in parallel (no DB session needed)
        progression, peer_benchmark = await asyncio.gather(
            _safe(self.get_rep_progression(user_id, company_id, weeks), "progression"),
            _safe(self.get_rep_peer_benchmark(user_id, company_id, days), "peer_benchmark"),
        )

        return CoachingDashboardResponse(
            team=team,
            issues=issues,
            strengths=strengths,
            progression=progression,
            peer_benchmark=peer_benchmark,
            impact=impact,
            objections=objections,
            nudges=nudges,
        )

    # =========================================================================
    # Split Dashboard Endpoints
    # =========================================================================

    async def get_team_dashboard(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        role_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> TeamDashboardResponse:
        """Fetch team-level coaching overview only."""

        async def _safe(coro, label: str):
            try:
                return await coro
            except Exception as e:
                logger.warning(f"Team dashboard section '{label}' failed: {e}")
                return None

        team = await _safe(
            self.get_team_overview(company_id, role_filter, search, start_date, end_date),
            "team",
        )
        return TeamDashboardResponse(team=team)

    async def get_individual_dashboard(
        self,
        user_id: UUID,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        weeks: int = 8,
        days: int = 30,
    ) -> IndividualDashboardResponse:
        """Fetch all 7 individual rep coaching sections.

        DB-dependent sections run sequentially (AsyncSession is not safe for
        concurrent use), while external Shunya API calls run in parallel.
        """

        async def _safe(coro, label: str):
            try:
                return await coro
            except Exception as e:
                logger.warning(f"Individual dashboard section '{label}' failed: {e}")
                return None

        # 1. Run DB-dependent sections sequentially (same session)
        issues = await _safe(self.get_rep_issues(user_id, company_id, start_date, end_date), "issues")
        strengths = await _safe(self.get_rep_strengths(user_id, company_id, start_date, end_date), "strengths")
        impact = await _safe(self.get_rep_impact(user_id, company_id), "impact")
        objections = await _safe(self.get_rep_objections(user_id, company_id, start_date, end_date), "objections")
        nudges = await _safe(self.get_rep_nudges(user_id, company_id, start_date, end_date), "nudges")

        # 2. Run external Shunya API calls in parallel (no DB session needed)
        progression, peer_benchmark = await asyncio.gather(
            _safe(self.get_rep_progression(user_id, company_id, weeks), "progression"),
            _safe(self.get_rep_peer_benchmark(user_id, company_id, days), "peer_benchmark"),
        )

        return IndividualDashboardResponse(
            issues=issues,
            strengths=strengths,
            progression=progression,
            peer_benchmark=peer_benchmark,
            impact=impact,
            objections=objections,
            nudges=nudges,
        )

    # =========================================================================
    # Team Overview
    # =========================================================================

    async def get_team_overview(
        self,
        company_id: UUID,
        role_filter: Optional[str] = None,
        search: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> TeamOverviewResponse:
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Get all active users for this company
        user_filters = [
            UserORM.company_id == company_id,
            UserORM.is_active == True,
        ]
        if role_filter:
            user_filters.append(func.lower(UserORM.role) == role_filter.lower())
        if search:
            search_pattern = f"%{search}%"
            user_filters.append(
                or_(
                    UserORM.first_name.ilike(search_pattern),
                    UserORM.last_name.ilike(search_pattern),
                    UserORM.email.ilike(search_pattern),
                )
            )

        users_result = await self.session.execute(
            select(UserORM).where(*user_filters)
        )
        users = users_result.scalars().all()

        if not users:
            return TeamOverviewResponse(
                stats=TeamStats(team_size=0),
                members=[],
            )

        user_ids = [u.id for u in users]

        # Batch query 1: call analysis stats for ALL users in one query (vs N separate queries before)
        analyses_result = await self.session.execute(
            select(
                CallORM.handled_by_user_id,
                func.avg(CallAnalysisORM.sop_compliance_score).label("avg_compliance"),
                func.count(CallORM.id).label("total_calls"),
                func.count(
                    case((func.lower(CallAnalysisORM.booking_status) == "booked", 1))
                ).label("booked_count"),
                func.count(
                    case(
                        (
                            CallAnalysisORM.qualification_status.in_(
                                ["hot", "warm", "cold", "qualified"]
                            ),
                            1,
                        )
                    )
                ).label("qualified_count"),
            )
            .select_from(CallORM)
            .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id.in_(user_ids),
                CallORM.company_id == company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt,
            )
            .group_by(CallORM.handled_by_user_id)
        )
        analyses_by_user = {row.handled_by_user_id: row for row in analyses_result}

        # Batch query 2: issues counts for ALL users in one query
        issues_result = await self.session.execute(
            select(
                CoachingIssueORM.user_id,
                func.count(CoachingIssueORM.id).label("count"),
            )
            .where(
                CoachingIssueORM.user_id.in_(user_ids),
                CoachingIssueORM.company_id == company_id,
                CoachingIssueORM.created_at >= start_dt,
                CoachingIssueORM.created_at <= end_dt,
            )
            .group_by(CoachingIssueORM.user_id)
        )
        issues_by_user = {row.user_id: row.count for row in issues_result}

        # Batch query 3: strengths counts for ALL users in one query
        strengths_result = await self.session.execute(
            select(
                CoachingStrengthORM.user_id,
                func.count(CoachingStrengthORM.id).label("count"),
            )
            .where(
                CoachingStrengthORM.user_id.in_(user_ids),
                CoachingStrengthORM.company_id == company_id,
                CoachingStrengthORM.created_at >= start_dt,
                CoachingStrengthORM.created_at <= end_dt,
            )
            .group_by(CoachingStrengthORM.user_id)
        )
        strengths_by_user = {row.user_id: row.count for row in strengths_result}

        # Batch queries 4 & 5: trend data for ALL users (first half vs second half compliance)
        mid_dt = start_dt + (end_dt - start_dt) / 2

        first_half_result = await self.session.execute(
            select(
                CallORM.handled_by_user_id,
                func.avg(CallAnalysisORM.sop_compliance_score).label("avg"),
            )
            .select_from(CallORM)
            .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id.in_(user_ids),
                CallORM.company_id == company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at < mid_dt,
                CallAnalysisORM.sop_compliance_score.isnot(None),
            )
            .group_by(CallORM.handled_by_user_id)
        )
        first_half_by_user = {row.handled_by_user_id: row.avg for row in first_half_result}

        second_half_result = await self.session.execute(
            select(
                CallORM.handled_by_user_id,
                func.avg(CallAnalysisORM.sop_compliance_score).label("avg"),
            )
            .select_from(CallORM)
            .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id.in_(user_ids),
                CallORM.company_id == company_id,
                CallORM.created_at >= mid_dt,
                CallORM.created_at <= end_dt,
                CallAnalysisORM.sop_compliance_score.isnot(None),
            )
            .group_by(CallORM.handled_by_user_id)
        )
        second_half_by_user = {row.handled_by_user_id: row.avg for row in second_half_result}

        # Build members list entirely from the batched data — no per-user DB calls
        members = []
        all_compliance = []
        all_booking_rates = []
        total_open_issues = 0

        for user in users:
            row = analyses_by_user.get(user.id)
            avg_compliance = float(row.avg_compliance or 0) if row else 0.0
            total_calls = int(row.total_calls or 0) if row else 0
            booked = int(row.booked_count or 0) if row else 0
            qualified = int(row.qualified_count or 0) if row else 0

            booking_rate = (booked / qualified * 100) if qualified > 0 else 0.0
            compliance_pct = round(avg_compliance * 100, 1) if avg_compliance else 0.0

            issues_count = issues_by_user.get(user.id, 0)
            strengths_count = strengths_by_user.get(user.id, 0)

            first_avg = first_half_by_user.get(user.id)
            second_avg = second_half_by_user.get(user.id)
            if first_avg is None or second_avg is None:
                trend = "stable"
            else:
                change = (second_avg - first_avg) / first_avg if first_avg > 0 else 0
                if change >= 0.05:
                    trend = "improving"
                elif change <= -0.05:
                    trend = "declining"
                else:
                    trend = "stable"

            if compliance_pct > 0:
                all_compliance.append(compliance_pct)
            if booking_rate > 0:
                all_booking_rates.append(booking_rate)
            total_open_issues += issues_count

            members.append(
                TeamMemberSummary(
                    user_id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    role=user.role,
                    compliance_pct=compliance_pct,
                    booking_rate_pct=round(booking_rate, 1),
                    total_calls=total_calls,
                    trend=trend,
                    issues_count=issues_count,
                    strengths_count=strengths_count,
                )
            )

        team_avg_compliance = (
            round(sum(all_compliance) / len(all_compliance), 1)
            if all_compliance
            else 0.0
        )
        team_avg_booking = (
            round(sum(all_booking_rates) / len(all_booking_rates), 1)
            if all_booking_rates
            else 0.0
        )

        stats = TeamStats(
            team_avg_compliance=team_avg_compliance,
            team_avg_booking_rate=team_avg_booking,
            open_issues=total_open_issues,
            team_size=len(members),
        )

        return TeamOverviewResponse(stats=stats, members=members)

    async def _compute_trend(
        self, user_id: UUID, company_id: UUID, start_dt: datetime, end_dt: datetime
    ) -> str:
        mid_dt = start_dt + (end_dt - start_dt) / 2

        first_half = await self.session.execute(
            select(func.avg(CallAnalysisORM.sop_compliance_score))
            .select_from(CallORM)
            .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id == user_id,
                CallORM.company_id == company_id,
                CallORM.created_at >= start_dt,
                CallORM.created_at < mid_dt,
                CallAnalysisORM.sop_compliance_score.isnot(None),
            )
        )
        second_half = await self.session.execute(
            select(func.avg(CallAnalysisORM.sop_compliance_score))
            .select_from(CallORM)
            .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id == user_id,
                CallORM.company_id == company_id,
                CallORM.created_at >= mid_dt,
                CallORM.created_at <= end_dt,
                CallAnalysisORM.sop_compliance_score.isnot(None),
            )
        )

        first_avg = first_half.scalar()
        second_avg = second_half.scalar()

        if first_avg is None or second_avg is None:
            return "stable"

        change = (second_avg - first_avg) / first_avg if first_avg > 0 else 0
        if change >= 0.05:
            return "improving"
        elif change <= -0.05:
            return "declining"
        return "stable"

    # =========================================================================
    # Issues Tab
    # =========================================================================

    async def get_rep_issues(
        self,
        user_id: UUID,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> RepIssuesResponse:
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Get user name
        user = await self.session.get(UserORM, user_id)
        rep_name = f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown"

        # Query all coaching issues for this user in date range
        result = await self.session.execute(
            select(CoachingIssueORM)
            .where(
                CoachingIssueORM.user_id == user_id,
                CoachingIssueORM.company_id == company_id,
                CoachingIssueORM.created_at >= start_dt,
                CoachingIssueORM.created_at <= end_dt,
            )
            .order_by(CoachingIssueORM.created_at.desc())
        )
        issues_rows = result.scalars().all()

        # Group by issue text (normalized)
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in issues_rows:
            key = row.issue.strip().lower()
            if key not in grouped:
                grouped[key] = {
                    "issue": row.issue,
                    "severity": row.severity,
                    "why_it_matters": row.why_it_matters,
                    "how_to_fix": row.how_to_fix,
                    "example_language": row.example_language,
                    "related_sop_metric": row.related_sop_metric,
                    "transcript_evidence": [],
                    "call_ids": [],
                    "count": 0,
                }
            grouped[key]["count"] += 1
            if row.transcript_evidence:
                grouped[key]["transcript_evidence"].append(row.transcript_evidence)
            grouped[key]["call_ids"].append(str(row.call_id))

        # Convert to response, sorted by frequency desc
        issues = []
        for data in sorted(grouped.values(), key=lambda x: x["count"], reverse=True):
            issues.append(
                CoachingIssueResponse(
                    issue=data["issue"],
                    severity=data["severity"],
                    frequency=data["count"],
                    why_it_matters=data["why_it_matters"],
                    how_to_fix=data["how_to_fix"],
                    example_language=data["example_language"],
                    transcript_evidence=data["transcript_evidence"][:5],
                    related_sop_metric=data["related_sop_metric"],
                    call_ids=list(set(data["call_ids"]))[:10],
                )
            )

        return RepIssuesResponse(
            rep_id=user_id,
            rep_name=rep_name,
            total_issues=len(issues),
            issues=issues,
        )

    # =========================================================================
    # Strengths Tab
    # =========================================================================

    async def get_rep_strengths(
        self,
        user_id: UUID,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> RepStrengthsResponse:
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        user = await self.session.get(UserORM, user_id)
        rep_name = f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown"

        result = await self.session.execute(
            select(CoachingStrengthORM)
            .where(
                CoachingStrengthORM.user_id == user_id,
                CoachingStrengthORM.company_id == company_id,
                CoachingStrengthORM.created_at >= start_dt,
                CoachingStrengthORM.created_at <= end_dt,
            )
            .order_by(CoachingStrengthORM.created_at.desc())
        )
        strengths_rows = result.scalars().all()

        grouped: Dict[str, Dict[str, Any]] = {}
        for row in strengths_rows:
            key = row.behavior.strip().lower()
            if key not in grouped:
                grouped[key] = {
                    "behavior": row.behavior,
                    "why_effective": row.why_effective,
                    "related_sop_metric": row.related_sop_metric,
                    "transcript_evidence": [],
                    "call_ids": [],
                    "count": 0,
                }
            grouped[key]["count"] += 1
            if row.transcript_evidence:
                grouped[key]["transcript_evidence"].append(row.transcript_evidence)
            grouped[key]["call_ids"].append(str(row.call_id))

        strengths = []
        for data in sorted(grouped.values(), key=lambda x: x["count"], reverse=True):
            strengths.append(
                CoachingStrengthResponse(
                    behavior=data["behavior"],
                    frequency=data["count"],
                    why_effective=data["why_effective"],
                    transcript_evidence=data["transcript_evidence"][:5],
                    related_sop_metric=data["related_sop_metric"],
                    call_ids=list(set(data["call_ids"]))[:10],
                )
            )

        return RepStrengthsResponse(
            rep_id=user_id,
            rep_name=rep_name,
            total_strengths=len(strengths),
            strengths=strengths,
        )

    # =========================================================================
    # Progression Tab (Shunya API proxy)
    # =========================================================================

    async def get_rep_progression(
        self,
        user_id: UUID,
        company_id: UUID,
        weeks: int = 8,
    ) -> Dict[str, Any]:
        rep_id = str(user_id)
        company_id_str = str(company_id)

        try:
            result = await self.shoonya.get_agent_progression(
                rep_id=rep_id,
                company_id=company_id_str,
                metrics="compliance_score,booking_rate",
                weeks=weeks,
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get progression from Shunya: {e}")
            raise

    # =========================================================================
    # Peer Benchmark Tab (Shunya API proxy)
    # =========================================================================

    async def get_rep_peer_benchmark(
        self,
        user_id: UUID,
        company_id: UUID,
        days: int = 30,
    ) -> RepPeerBenchmarkResponse:
        rep_id = str(user_id)
        company_id_str = str(company_id)

        metrics_to_fetch = [
            "compliance_score",
            "booking_rate",
            "objection_handling",
            "rapport_score",
            "script_adherence",
        ]

        # Fetch user record first (DB), then Shunya metrics in parallel (HTTP)
        try:
            user = await self.session.get(UserORM, user_id)
        except Exception:
            user = None

        tasks = [
            self.shoonya.get_agent_peer_comparison(
                rep_id=rep_id,
                company_id=company_id_str,
                metric=metric,
                days=days,
            )
            for metric in metrics_to_fetch
        ]

        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        results = all_results

        benchmark_metrics = []
        for i, result in enumerate(results):
            metric_name = metrics_to_fetch[i]
            if isinstance(result, Exception):
                logger.warning(f"Failed to get peer comparison for {metric_name}: {result}")
                benchmark_metrics.append(
                    PeerBenchmarkMetric(metric=metric_name)
                )
                continue

            rep_score = result.get("rep_score", 0)
            peer_avg = result.get("peer_average", 0)
            peer_max = result.get("peer_max", 0)

            benchmark_metrics.append(
                PeerBenchmarkMetric(
                    metric=metric_name,
                    rank=result.get("rep_rank", 0),
                    percentile=result.get("percentile", 0),
                    rep_score=round(rep_score * 100, 1) if rep_score <= 1 else round(rep_score, 1),
                    peer_average=round(peer_avg * 100, 1) if peer_avg <= 1 else round(peer_avg, 1),
                    top_score=round(peer_max * 100, 1) if peer_max <= 1 else round(peer_max, 1),
                    gap_to_top=round((peer_max - rep_score) * 100, 1) if peer_max <= 1 else round(peer_max - rep_score, 1),
                    vs_avg=round((rep_score - peer_avg) * 100, 1) if peer_avg <= 1 else round(rep_score - peer_avg, 1),
                )
            )

        rep_name = f"{user.first_name or ''} {user.last_name or ''}".strip() if user and not isinstance(user, Exception) else None

        return RepPeerBenchmarkResponse(
            rep_id=rep_id,
            rep_name=rep_name,
            company_id=company_id_str,
            metrics=benchmark_metrics,
        )

    # =========================================================================
    # Impact Tab
    # =========================================================================

    async def get_rep_impact(
        self,
        user_id: UUID,
        company_id: UUID,
    ) -> RepImpactResponse:
        user = await self.session.get(UserORM, user_id)
        rep_name = f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown"

        result = await self.session.execute(
            select(CoachingSessionORM)
            .where(
                CoachingSessionORM.rep_user_id == user_id,
                CoachingSessionORM.company_id == company_id,
            )
            .order_by(CoachingSessionORM.coached_at.desc())
        )
        sessions = result.scalars().all()

        session_summaries = []
        now = datetime.now(timezone.utc)
        for s in sessions:
            days_into = None
            if s.follow_up_end_date and s.coached_at:
                elapsed = now - s.coached_at.replace(tzinfo=timezone.utc) if s.coached_at.tzinfo is None else now - s.coached_at
                days_into = max(0, elapsed.days)

            session_summaries.append(
                CoachingSessionSummary(
                    session_id=s.id,
                    coached_at=s.coached_at,
                    focus_areas=s.focus_areas or [],
                    status=s.status,
                    follow_up_days=s.follow_up_days,
                    follow_up_end_date=s.follow_up_end_date,
                    baseline_scores=s.baseline_scores,
                    impact_scores=s.impact_scores,
                    overall_improved=s.overall_improved,
                    improvement_pct=s.improvement_pct,
                    targets_met=s.targets_met,
                    days_into_follow_up=days_into,
                )
            )

        return RepImpactResponse(
            rep_id=user_id,
            rep_name=rep_name,
            sessions=session_summaries,
        )

    # =========================================================================
    # Objections Tab
    # =========================================================================

    async def get_rep_objections(
        self,
        user_id: UUID,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> RepObjectionsResponse:
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

        user = await self.session.get(UserORM, user_id)
        rep_name = f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Unknown"

        # Get rep's objections grouped by category
        rep_objections = await self.session.execute(
            select(
                CallObjectionDetailORM.category_text,
                func.count(CallObjectionDetailORM.id).label("total"),
                func.count(
                    case((CallObjectionDetailORM.overcome == True, 1))
                ).label("overcome"),
            )
            .where(
                CallObjectionDetailORM.user_id == user_id,
                CallObjectionDetailORM.company_id == company_id,
                CallObjectionDetailORM.created_at >= start_dt,
                CallObjectionDetailORM.created_at <= end_dt,
            )
            .group_by(CallObjectionDetailORM.category_text)
        )
        rep_data = {row.category_text: {"total": row.total, "overcome": row.overcome} for row in rep_objections}

        # Get team averages
        team_objections = await self.session.execute(
            select(
                CallObjectionDetailORM.category_text,
                func.count(CallObjectionDetailORM.id).label("total"),
                func.count(
                    case((CallObjectionDetailORM.overcome == True, 1))
                ).label("overcome"),
            )
            .where(
                CallObjectionDetailORM.company_id == company_id,
                CallObjectionDetailORM.created_at >= start_dt,
                CallObjectionDetailORM.created_at <= end_dt,
            )
            .group_by(CallObjectionDetailORM.category_text)
        )
        team_data = {row.category_text: {"total": row.total, "overcome": row.overcome} for row in team_objections}

        # Build categories
        categories = []
        total_objections = 0
        all_categories = set(rep_data.keys()) | set(team_data.keys())

        for cat in sorted(all_categories):
            rep = rep_data.get(cat, {"total": 0, "overcome": 0})
            team = team_data.get(cat, {"total": 0, "overcome": 0})

            if rep["total"] == 0:
                continue

            rep_rate = rep["overcome"] / rep["total"] if rep["total"] > 0 else 0
            team_rate = team["overcome"] / team["total"] if team["total"] > 0 else 0
            total_objections += rep["total"]

            categories.append(
                ObjectionCategory(
                    category=cat,
                    total_count=rep["total"],
                    overcome_count=rep["overcome"],
                    rep_overcome_rate=round(rep_rate * 100, 1),
                    team_avg_overcome_rate=round(team_rate * 100, 1),
                    delta_vs_team=round((rep_rate - team_rate) * 100, 1),
                )
            )

        # Sort by most frequent
        categories.sort(key=lambda x: x.total_count, reverse=True)

        return RepObjectionsResponse(
            rep_id=user_id,
            rep_name=rep_name,
            total_objections=total_objections,
            categories=categories,
        )

    # =========================================================================
    # Smart Nudges Tab
    # =========================================================================

    async def get_rep_nudges(
        self,
        user_id: UUID,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> RepSmartNudgesResponse:
        if not start_date:
            start_date = date.today() - timedelta(days=30)
        if not end_date:
            end_date = date.today()

        # Fetch issues and objections sequentially (AsyncSession not safe for concurrent use)
        issues_resp = await self.get_rep_issues(user_id, company_id, start_date, end_date)
        objections_resp = await self.get_rep_objections(user_id, company_id, start_date, end_date)
        rep_name = issues_resp.rep_name

        nudges: List[SmartNudge] = []

        # 1. High-frequency issues -> Immediate nudges
        for issue in issues_resp.issues:
            if issue.frequency >= 3 and issue.severity == "high":
                nudges.append(
                    SmartNudge(
                        title=issue.issue[:80],
                        message=issue.how_to_fix or f"This issue appeared in {issue.frequency} calls. Review the SOP and practice the recommended approach.",
                        priority="high",
                        timing="immediate",
                        source="coaching_issues",
                    )
                )
            elif issue.frequency >= 2:
                nudges.append(
                    SmartNudge(
                        title=issue.issue[:80],
                        message=issue.how_to_fix or f"Recurring issue ({issue.frequency} calls). Focus on improving this area.",
                        priority="medium",
                        timing="immediate",
                        source="coaching_issues",
                    )
                )

        # 2. Low overcome rate objections -> Pre Call nudges
        for cat in objections_resp.categories:
            if cat.rep_overcome_rate < 30 and cat.total_count >= 3:
                nudges.append(
                    SmartNudge(
                        title=f"Upcoming Call: {cat.category}",
                        message=f"You overcome '{cat.category}' objections only {cat.rep_overcome_rate:.0f}% of the time (team avg: {cat.team_avg_overcome_rate:.0f}%). Practice the value framework for this objection type.",
                        priority="high" if cat.delta_vs_team < -20 else "medium",
                        timing="pre_call",
                        source="objection_history",
                    )
                )

        # 3. Compliance trend nudge
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        trend = await self._compute_trend(user_id, company_id, start_dt, end_dt)
        if trend == "declining":
            nudges.append(
                SmartNudge(
                    title="Weekly Progress Update",
                    message="Your compliance score has been declining. Review recent call recordings and focus on SOP adherence.",
                    priority="medium",
                    timing="weekly",
                    source="progression",
                )
            )
        elif trend == "improving":
            nudges.append(
                SmartNudge(
                    title="Weekly Progress Update",
                    message="Your compliance score is improving! Keep reinforcing your discovery questions - they're driving better outcomes.",
                    priority="low",
                    timing="weekly",
                    source="progression",
                )
            )

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        nudges.sort(key=lambda n: priority_order.get(n.priority, 1))

        return RepSmartNudgesResponse(
            rep_id=user_id,
            rep_name=rep_name,
            nudges=nudges,
        )

    # =========================================================================
    # Coaching Sessions CRUD
    # =========================================================================

    async def create_coaching_session(
        self,
        company_id: UUID,
        rep_user_id: UUID,
        coach_user_id: UUID,
        focus_areas: List[str],
        targets: Dict[str, float],
        follow_up_days: int = 7,
        notes: Optional[str] = None,
    ) -> CoachingSessionORM:
        now = datetime.now(timezone.utc)

        # Auto-compute baseline from recent call analyses
        baseline_scores = await self._compute_baseline(rep_user_id, company_id, focus_areas)

        session = CoachingSessionORM(
            company_id=company_id,
            rep_user_id=rep_user_id,
            coach_user_id=coach_user_id,
            focus_areas=focus_areas,
            targets=targets,
            baseline_scores=baseline_scores,
            status="in_progress",
            follow_up_days=follow_up_days,
            follow_up_end_date=now + timedelta(days=follow_up_days),
            notes=notes,
            coached_at=now,
        )
        self.session.add(session)
        await self.session.commit()
        await self.session.refresh(session)
        return session

    async def _compute_baseline(
        self,
        user_id: UUID,
        company_id: UUID,
        focus_areas: List[str],
    ) -> Dict[str, float]:
        """Compute baseline scores from the last 5 completed call analyses."""
        result = await self.session.execute(
            select(CallAnalysisORM)
            .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
            .where(
                CallORM.handled_by_user_id == user_id,
                CallORM.company_id == company_id,
                CallAnalysisORM.status == "completed",
                CallAnalysisORM.sop_compliance_score.isnot(None),
            )
            .order_by(CallORM.created_at.desc())
            .limit(5)
        )
        analyses = result.scalars().all()

        if not analyses:
            return {}

        scores: Dict[str, List[float]] = defaultdict(list)
        for a in analyses:
            if a.sop_compliance_score is not None:
                scores["compliance_score"].append(a.sop_compliance_score)
            if a.booking_status:
                scores["booking_rate"].append(1.0 if a.booking_status.lower() == "booked" else 0.0)
            if a.sentiment_score is not None:
                scores["rapport_score"].append(a.sentiment_score)

        baseline = {}
        for metric, values in scores.items():
            if values:
                baseline[metric] = round(sum(values) / len(values), 3)

        return baseline

    async def list_coaching_sessions(
        self,
        company_id: UUID,
        rep_user_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CoachingSessionListResponse:
        filters = [CoachingSessionORM.company_id == company_id]
        if rep_user_id:
            filters.append(CoachingSessionORM.rep_user_id == rep_user_id)
        if status:
            filters.append(CoachingSessionORM.status == status)

        # Count total
        count_result = await self.session.execute(
            select(func.count(CoachingSessionORM.id)).where(*filters)
        )
        total = count_result.scalar() or 0

        # Fetch sessions
        result = await self.session.execute(
            select(CoachingSessionORM)
            .where(*filters)
            .order_by(CoachingSessionORM.coached_at.desc())
            .limit(limit)
            .offset(offset)
        )
        sessions = result.scalars().all()

        session_responses = [
            CoachingSessionResponse(
                id=s.id,
                company_id=s.company_id,
                rep_user_id=s.rep_user_id,
                coach_user_id=s.coach_user_id,
                focus_areas=s.focus_areas or [],
                targets=s.targets,
                baseline_scores=s.baseline_scores,
                status=s.status,
                follow_up_days=s.follow_up_days,
                follow_up_end_date=s.follow_up_end_date,
                impact_scores=s.impact_scores,
                overall_improved=s.overall_improved,
                improvement_pct=s.improvement_pct,
                targets_met=s.targets_met,
                notes=s.notes,
                coached_at=s.coached_at,
                created_at=s.created_at,
            )
            for s in sessions
        ]

        return CoachingSessionListResponse(total=total, sessions=session_responses)
