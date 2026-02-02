"""
Pending action service.

Provides business logic for managing pending actions:
- Fetching by urgency
- Marking as completed/converted
- Conversion metrics
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.pending_action import PendingAction
from app.domain.enums import PendingActionStatus
from app.infrastructure.repositories.pending_action import PendingActionRepository

logger = get_logger(__name__)


class PendingActionService:
    """Service for pending action operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.pending_action_repo = PendingActionRepository(session)
    
    async def fetch_by_urgency(
        self,
        company_id: UUID,
        limit: int = 100,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Fetch pending actions sorted by urgency (due_at + priority).
        
        Args:
            company_id: Company ID
            limit: Maximum number of actions to return
            status: Optional status filter (defaults to PENDING)
            
        Returns:
            List of pending actions sorted by urgency
        """
        try:
            return await self.pending_action_repo.get_by_urgency(
                company_id=company_id,
                limit=limit,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error fetching pending actions by urgency: {e}")
            raise e
    
    async def mark_completed(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Mark a pending action as completed.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.COMPLETED,
            )
        except Exception as e:
            logger.error(f"Error marking action as completed: {e}", action_id=str(action_id))
            raise e
    
    async def reopen(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Reopen a pending action (set status back to pending).
        Use when a CSR or sales rep mistakenly marked an action as complete.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.PENDING,
            )
        except Exception as e:
            logger.error(f"Error reopening pending action: {e}", action_id=str(action_id))
            raise e
    
    async def mark_converted(
        self,
        action_id: UUID,
    ) -> Optional[PendingAction]:
        """
        Mark a pending action as converted.
        
        Args:
            action_id: Action ID
            
        Returns:
            Updated pending action or None if not found
        """
        try:
            return await self.pending_action_repo.update_status(
                action_id=action_id,
                status=PendingActionStatus.CONVERTED,
            )
        except Exception as e:
            logger.error(f"Error marking action as converted: {e}", action_id=str(action_id))
            raise e
    
    async def get_conversion_metrics(
        self,
        company_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get conversion metrics (pending → converted).
        
        Args:
            company_id: Company ID
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            Dict with conversion metrics
        """
        try:
            # Convert dates to datetimes if provided
            start_dt = None
            end_dt = None
            if start_date:
                start_dt = datetime.combine(start_date, datetime.min.time())
            if end_date:
                end_dt = datetime.combine(end_date, datetime.max.time())
            
            return await self.pending_action_repo.get_conversion_metrics(
                company_id=company_id,
                start_date=start_dt,
                end_date=end_dt,
            )
        except Exception as e:
            logger.error(f"Error getting conversion metrics: {e}")
            raise e
    
    async def get_by_company(
        self,
        company_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """
        Get all pending actions for a company.
        
        Args:
            company_id: Company ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_company(
                company_id=company_id,
                status=status,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by company: {e}")
            raise e
    
    async def get_by_lead(
        self,
        lead_id: UUID,
        status: Optional[PendingActionStatus] = None,
    ) -> List[PendingAction]:
        """
        Get all pending actions for a lead.
        
        Args:
            lead_id: Lead ID
            status: Optional status filter
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_lead(
                lead_id=lead_id,
                status=status,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by lead: {e}")
            raise e
    
    async def get_by_owner(
        self,
        owner_id: UUID,
        status: Optional[PendingActionStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[PendingAction]:
        """
        Get all pending actions for an owner/user.
        
        Args:
            owner_id: Owner/user ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of pending actions
        """
        try:
            return await self.pending_action_repo.get_by_owner(
                owner_id=owner_id,
                status=status,
                skip=skip,
                limit=limit,
            )
        except Exception as e:
            logger.error(f"Error getting pending actions by owner: {e}")
            raise e

    async def create_from_call(
        self,
        call_id: UUID,
        company_id: UUID,
        lead_id: Optional[UUID],
        owner_id: UUID,
        assigned_by_id: UUID,
        action_type: str,
        raw_text: Optional[str] = None,
        due_at: Optional[datetime] = None,
        priority: Optional[int] = None,
    ) -> PendingAction:
        """
        Create a pending action linked to a call, assigned to a user (e.g. executive assigning to CSR).
        
        Args:
            call_id: Call this action is tied to
            company_id: Company ID
            lead_id: Lead ID from the call (optional)
            owner_id: User to assign the action to (CSR)
            assigned_by_id: User creating/assigning the action (e.g. executive)
            action_type: Type of action
            raw_text: Optional description
            due_at: Optional due date
            priority: Optional priority
        Returns:
            Created PendingAction
        """
        pending = PendingAction(
            company_id=company_id,
            lead_id=lead_id,
            call_id=call_id,
            appointment_id=None,
            action_type=action_type,
            raw_text=raw_text,
            status=PendingActionStatus.PENDING,
            due_at=due_at,
            priority=priority,
            owner_id=owner_id,
            assigned_by_id=assigned_by_id,
            source="manual",
            extra_metadata=None,
        )
        return await self.pending_action_repo.create(pending)
