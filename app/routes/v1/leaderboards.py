"""
Leaderboard API.

Single retrieval endpoint with background recalculation.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query

from app.core.dependencies import DbSession, CurrentUser
from app.services.leaderboard import LeaderboardService
from app.domain.models.leaderboard import LeaderboardEntry
from app.infrastructure.database.session import AsyncSessionLocal

router = APIRouter()


async def _recalculate_leaderboard_background(company_id: UUID) -> None:
    """Run leaderboard stats recalculation in background (own session)."""
    async with AsyncSessionLocal() as session:
        try:
            service = LeaderboardService(session)
            await service.recalculate_stats(company_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.get(
    "",
    response_model=list[LeaderboardEntry],
    summary="Get leaderboard",
    description="Returns leaderboard for the current user's company. Triggers background recalculation for next retrieval.",
)
async def get_leaderboard(
    db: DbSession,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    period: str = Query(
        "all_time",
        description="Period: 'all_time' or YYYY-MM (e.g. 2024-05)",
    ),
) -> list[LeaderboardEntry]:
    """
    Get leaderboard for the authenticated user's company.
    Stats are recalculated in the background for the next request.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=403,
            detail="User has no company; leaderboard requires company context",
        )
    # Run recalculation in background (next read will see fresh data)
    background_tasks.add_task(
        _recalculate_leaderboard_background,
        company_id,
    )
    service = LeaderboardService(db)
    return await service.get_leaderboard(company_id, period)
