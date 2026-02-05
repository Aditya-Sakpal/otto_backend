"""
Leaderboard repository.

Reads from leaderboard_stats; recalculate aggregates from appointments and leads.
"""
from datetime import datetime
from typing import List
from uuid import UUID

from sqlalchemy import select, func, delete, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.database.models.leaderboard_stats import LeaderboardStatsORM
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.database.models.lead import LeadORM

logger = get_logger(__name__)


def _month_key(dt: datetime) -> str:
    """Return YYYY-MM for a datetime."""
    return dt.strftime("%Y-%m")


class LeaderboardRepository:
    """Repository for leaderboard stats (read + recalc)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_stats_for_period(
        self, company_id: UUID, period_key: str
    ) -> List[LeaderboardStatsORM]:
        """Get all leaderboard_stats rows for a company and period."""
        result = await self.session.execute(
            select(LeaderboardStatsORM).where(
                and_(
                    LeaderboardStatsORM.company_id == company_id,
                    LeaderboardStatsORM.period_key == period_key,
                )
            )
        )
        return list(result.scalars().all())

    async def recalculate_stats(self, company_id: UUID) -> None:
        """
        Recompute leaderboard_stats from appointments and leads for this company.
        Updates both current month (YYYY-MM) and all_time.
        """
        now = datetime.utcnow()
        current_month = _month_key(now)

        for period_key, month_start, month_end in [
            (current_month, datetime(now.year, now.month, 1), now),
            ("all_time", None, None),
        ]:
            # Appointments: won_count, total_resolved, no_show_count by assigned_rep_id
            appt_base = (
                select(
                    AppointmentORM.assigned_rep_id,
                    func.sum(
                        case((AppointmentORM.outcome == "won", 1), else_=0)
                    ).label("won_count"),
                    func.sum(
                        case(
                            (
                                AppointmentORM.outcome.in_(
                                    ["won", "lost", "no_show"]
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ).label("total_resolved"),
                    func.sum(
                        case((AppointmentORM.outcome == "no_show", 1), else_=0)
                    ).label("no_show_count"),
                )
                .where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.assigned_rep_id.isnot(None),
                )
                .group_by(AppointmentORM.assigned_rep_id)
            )
            if month_start is not None and month_end is not None:
                appt_base = appt_base.where(
                    AppointmentORM.scheduled_start >= month_start,
                    AppointmentORM.scheduled_start <= month_end,
                )
            appt_result = await self.session.execute(appt_base)
            appt_rows = appt_result.all()

            # Leads: sum_deal_value by assigned_rep_id (closed_won)
            lead_base = (
                select(
                    LeadORM.assigned_rep_id,
                    func.coalesce(func.sum(LeadORM.deal_size), 0).label(
                        "sum_deal_value"
                    ),
                )
                .where(
                    LeadORM.company_id == company_id,
                    LeadORM.status == "closed_won",
                    LeadORM.assigned_rep_id.isnot(None),
                )
                .group_by(LeadORM.assigned_rep_id)
            )
            if month_start is not None and month_end is not None:
                lead_base = lead_base.where(
                    LeadORM.closed_at.isnot(None),
                    LeadORM.closed_at >= month_start,
                    LeadORM.closed_at <= month_end,
                )
            lead_result = await self.session.execute(lead_base)
            lead_sums = {r[0]: float(r[1]) for r in lead_result.all()}

            # Build (user_id -> stats) for this period
            by_user: dict[UUID, dict] = {}
            for row in appt_rows:
                uid = row[0]
                by_user[uid] = {
                    "won_count": int(row[1] or 0),
                    "total_resolved": int(row[2] or 0),
                    "no_show_count": int(row[3] or 0),
                    "sum_deal_value": lead_sums.get(uid, 0.0),
                }
            # Include reps that only have leads (no appointments)
            for uid in lead_sums:
                if uid not in by_user:
                    by_user[uid] = {
                        "won_count": 0,
                        "total_resolved": 0,
                        "no_show_count": 0,
                        "sum_deal_value": lead_sums[uid],
                    }

            if not by_user:
                continue

            # Delete existing rows for this company + period
            await self.session.execute(
                delete(LeaderboardStatsORM).where(
                    and_(
                        LeaderboardStatsORM.company_id == company_id,
                        LeaderboardStatsORM.period_key == period_key,
                    )
                )
            )
            # Insert new rows
            for user_id, stats in by_user.items():
                row = LeaderboardStatsORM(
                    user_id=user_id,
                    company_id=company_id,
                    period_key=period_key,
                    won_count=stats["won_count"],
                    total_resolved=stats["total_resolved"],
                    sum_deal_value=stats["sum_deal_value"],
                    no_show_count=stats["no_show_count"],
                )
                self.session.add(row)
        await self.session.flush()
        logger.info(f"Recalculated leaderboard_stats for company {company_id}")
