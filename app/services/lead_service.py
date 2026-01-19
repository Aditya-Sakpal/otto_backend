"""
Lead service.

Orchestrates lead-related business logic.
"""
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.lead import Lead
from app.domain.models.lead_detail import LeadDetail
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
    
    async def get_detail_by_id(self, lead_id: UUID) -> Optional[LeadDetail]:
        """Get detailed lead information for lead details page."""
        return await self.lead_repo.get_detail_by_id(lead_id)
    
    async def assign_to_rep(
        self,
        lead_id: UUID,
        sales_rep_id: UUID,
        assigned_by_user_id: UUID,
    ) -> Optional[Lead]:
        """
        Assign a lead to a sales rep.
        
        Validates that:
        - Lead exists
        - Sales rep exists and has sales_rep role
        - Both belong to the same company
        """
        from app.infrastructure.database.models.user import UserORM
        from app.infrastructure.database.models.lead import LeadORM
        from sqlalchemy import select
        
        # Get the lead to verify it exists and get company_id
        lead_result = await self.session.execute(
            select(LeadORM).where(LeadORM.id == lead_id)
        )
        lead_orm = lead_result.scalar_one_or_none()
        
        if not lead_orm:
            return None
        
        # Get the sales rep to verify they exist and have the correct role
        rep_result = await self.session.execute(
            select(UserORM).where(
                UserORM.id == sales_rep_id,
                UserORM.role == "sales_rep",
                UserORM.is_active == True,
            )
        )
        rep_orm = rep_result.scalar_one_or_none()
        
        if not rep_orm:
            raise ValueError(f"Sales rep with ID {sales_rep_id} not found or not active")
        
        # Verify both belong to the same company
        if lead_orm.company_id != rep_orm.company_id:
            raise ValueError("Lead and sales rep must belong to the same company")
        
        # Assign the lead
        return await self.lead_repo.assign_to_rep(
            lead_id=lead_id,
            sales_rep_id=sales_rep_id,
            assigned_by_user_id=assigned_by_user_id,
        )

