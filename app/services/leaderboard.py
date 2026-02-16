"""
Leaderboard service.

Retrieval from leaderboard_stats with normalization and scoring.
Background recalculation from appointments and leads.
"""
import math
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.leaderboard import LeaderboardEntry
from app.infrastructure.database.models.leaderboard_stats import LeaderboardStatsORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.repositories.leaderboard import LeaderboardRepository

# Weights per context.md: 40% Win Rate, 35% Deal Size, 15% Attendance, 10% Follow-up
WEIGHT_WIN_RATE = 0.40
WEIGHT_DEAL_SIZE = 0.35
WEIGHT_ATTENDANCE = 0.15
WEIGHT_FOLLOW_UP = 0.10  # Placeholder; not in leaderboard_stats yet


def _safe_log(x: float) -> float:
    """Log with guard for zero/negative."""
    if x is None or x <= 0:
        return 0.0
    return math.log(x)


def _normalize_linear(val: float, min_val: float, max_val: float) -> float:
    """Linear normalization to [0, 1]. Default (0, 1) if range is zero."""
    if max_val is None or min_val is None:
        return 0.0
    span = max_val - min_val
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (val - min_val) / span))


def _normalize_log(val: float, min_val: float, max_val: float) -> float:
    """Log normalization to [0, 1]. Default (0, 1) if range is zero."""
    if val is None or val <= 0:
        return 0.0
    log_min = _safe_log(min_val) if min_val and min_val > 0 else 0.0
    log_max = _safe_log(max_val) if max_val and max_val > 0 else 1.0
    span = log_max - log_min
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (_safe_log(val) - log_min) / span))


class LeaderboardService:
    """Service for leaderboard retrieval and background recalculation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.leaderboard_repo = LeaderboardRepository(session)

    async def get_leaderboard(
        self, company_id: UUID, period_key: str
    ) -> List[LeaderboardEntry]:
        """
        Get leaderboard for a company and period.
        Applies normalization and composite score (0–100), sorted by score desc.
        """
        rows = await self.leaderboard_repo.get_stats_for_period(
            company_id, period_key
        )
        if not rows:
            return []

        # Compute raw metrics per rep
        win_rates: List[float] = []
        deal_values: List[float] = []
        attendance_pcts: List[float] = []

        for r in rows:
            rate = (
                (r.won_count / r.total_resolved * 100.0)
                if r.total_resolved
                else 0.0
            )
            win_rates.append(rate)
            deal_values.append(r.sum_deal_value or 0.0)
            total_appts = r.total_resolved + (
                r.no_show_count
            )  # resolved = won+lost+no_show, so total with outcome
            # Actually total_resolved is won+lost+no_show; total appointments with outcome
            # Attendance = 1 - no_show_rate. So attendance_pct = (total_resolved - no_show_count) / total_resolved * 100 if total_resolved else 100
            total_with_outcome = r.total_resolved
            if total_with_outcome:
                attendance_pcts.append(
                    (total_with_outcome - r.no_show_count)
                    / total_with_outcome
                    * 100.0
                )
            else:
                attendance_pcts.append(100.0)

        min_rate = min(win_rates) if win_rates else 0.0
        max_rate = max(win_rates) if win_rates else 1.0
        positive_deals = [d for d in deal_values if d > 0]
        min_deal = min(positive_deals, default=1.0) if positive_deals else 1.0
        max_deal = max(deal_values, default=1.0) if deal_values else 1.0
        min_att = min(attendance_pcts) if attendance_pcts else 0.0
        max_att = max(attendance_pcts) if attendance_pcts else 100.0

        if max_rate - min_rate <= 0:
            max_rate = min_rate + 1.0
        if max_deal <= 0 or _safe_log(max_deal) - _safe_log(min_deal) <= 0:
            min_deal, max_deal = 0.0, 1.0
        if max_att - min_att <= 0:
            max_att = min_att + 1.0

        # Fetch display names for user_ids
        user_ids = [r.user_id for r in rows]
        result = await self.session.execute(
            select(UserORM.id, UserORM.first_name, UserORM.last_name).where(
                UserORM.id.in_(user_ids)
            )
        )
        user_map = {}
        for u in result.all():
            name = " ".join(
                filter(None, [u[1], u[2]])
            ).strip() or None
            user_map[u[0]] = name

        # Score each rep
        scored: List[tuple[float, LeaderboardStatsORM, float, float, float]] = []
        for i, r in enumerate(rows):
            rate = win_rates[i]
            deal = deal_values[i]
            att = attendance_pcts[i]
            z_win = _normalize_linear(rate, min_rate, max_rate)
            z_deal = _normalize_log(deal, min_deal, max_deal)
            z_att = _normalize_linear(att, min_att, max_att)
            follow_up = 0.0  # placeholder
            score = (
                WEIGHT_WIN_RATE * z_win
                + WEIGHT_DEAL_SIZE * z_deal
                + WEIGHT_ATTENDANCE * z_att
                + WEIGHT_FOLLOW_UP * follow_up
            ) * 100.0
            scored.append((score, r, rate, deal, att))

        scored.sort(key=lambda x: -x[0])

        return [
            LeaderboardEntry(
                rank=rank,
                user_id=s[1].user_id,
                display_name=user_map.get(s[1].user_id),
                score=round(s[0], 2),
                win_rate=round(s[2], 2),
                sum_deal_value=round(s[3], 2),
                attendance_pct=round(s[4], 2),
            )
            for rank, s in enumerate(scored, start=1)
        ]

    async def recalculate_stats(self, company_id: UUID) -> None:
        """Recalculate leaderboard_stats from appointments and leads (for background task)."""
        await self.leaderboard_repo.recalculate_stats(company_id)
