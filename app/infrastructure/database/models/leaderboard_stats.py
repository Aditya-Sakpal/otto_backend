"""
Leaderboard stats ORM model (accumulator table).
"""
from sqlalchemy import String, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID

from app.infrastructure.database.base import Base


class LeaderboardStatsORM(Base):
    """Pre-aggregated leaderboard stats per user per company per period."""

    __tablename__ = "leaderboard_stats"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    period_key: Mapped[str] = mapped_column(String(20), primary_key=True)
    won_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sum_deal_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    no_show_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
