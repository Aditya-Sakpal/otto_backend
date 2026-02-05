"""
Leaderboard domain model (API response).
"""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LeaderboardEntry(BaseModel):
    """Single leaderboard entry for retrieval."""

    rank: int = Field(..., description="1-based rank")
    user_id: UUID = Field(..., description="Sales rep user ID")
    display_name: Optional[str] = Field(None, description="Rep display name")
    score: float = Field(..., description="Composite score 0-100")
    win_rate: float = Field(..., description="Resolved win rate (0-100)")
    sum_deal_value: float = Field(..., description="Total deal value")
    attendance_pct: float = Field(..., description="Attendance % (1 - no_show rate)")

    model_config = {"from_attributes": True}
