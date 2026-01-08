"""
Lead service.

Orchestrates lead-related business logic.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.infrastructure.repositories.lead import LeadRepository

logger = get_logger(__name__)


class LeadService:
    """Service for lead-related operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.lead_repo = LeadRepository(session)
    
    async def get_by_id(self, lead_id: UUID) -> Optional[Lead]:
        """Get lead by ID."""
        return await self.lead_repo.get_by_id(lead_id)
    
    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get all leads for a company."""
        return await self.lead_repo.get_by_company(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
    
    async def get_by_statuses(
        self,
        company_id: UUID,
        statuses: List[str],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads by status filter."""
        return await self.lead_repo.get_by_statuses(
            company_id=company_id,
            statuses=statuses,
            skip=skip,
            limit=limit,
        )
    
    async def get_unbooked(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get qualified_unbooked leads."""
        return await self.lead_repo.get_unbooked(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
    
    async def get_by_priority(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get leads sorted by priority."""
        return await self.lead_repo.get_by_priority(
            company_id=company_id,
            skip=skip,
            limit=limit,
        )
    
    async def get_nurturing(
        self,
        company_id: UUID,
        statuses: Optional[List[str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get nurturing leads (new, warm, hot)."""
        if statuses is None:
            statuses = ["new", "warm", "hot"]
        return await self.lead_repo.get_by_statuses(
            company_id=company_id,
            statuses=statuses,
            skip=skip,
            limit=limit,
        )
    
    async def get_lost(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Lead]:
        """Get lost leads (closed_lost, abandoned, dormant)."""
        return await self.lead_repo.get_by_statuses(
            company_id=company_id,
            statuses=["closed_lost", "abandoned", "dormant"],
            skip=skip,
            limit=limit,
        )

