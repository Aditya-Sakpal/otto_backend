"""
Call analysis repository.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.models.analysis import CallAnalysis
from app.domain.enums import ObjectionType, SOPStage, AnalysisStatus
from app.infrastructure.database.models.analysis import CallAnalysisORM
from app.infrastructure.repositories.base import BaseRepository

logger = get_logger(__name__)


class CallAnalysisRepository(BaseRepository[CallAnalysisORM, CallAnalysis]):
    """Repository for CallAnalysis entities."""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, CallAnalysisORM, CallAnalysis)
    
    async def get_by_call_id(self, call_id: UUID) -> Optional[CallAnalysis]:
        """Get analysis by call ID."""
        try:
            result = await self.session.execute(
                select(CallAnalysisORM).where(CallAnalysisORM.call_id == call_id)
            )
            orm_obj = result.scalar_one_or_none()
            if orm_obj:
                return self._to_domain(orm_obj)
            return None
        except Exception as e:
            logger.error(f"Error getting analysis by call ID: {e}")
            raise e
    
    async def get_by_company(
        self,
        company_id: UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CallAnalysis]:
        """Get all analyses for a company."""
        try:
            return await self.get_all(
                skip=skip,
                limit=limit,
                filters={"company_id": company_id},
            )
        except Exception as e:
            logger.error(f"Error getting analyses by company: {e}")
            raise e
    
    async def upsert_by_call_id(
        self,
        call_id: UUID,
        analysis: CallAnalysis,
    ) -> CallAnalysis:
        """
        Create or update analysis by call ID.
        
        Args:
            call_id: Call ID
            analysis: Analysis data
            
        Returns:
            Created or updated analysis
        """
        try:
            existing = await self.get_by_call_id(call_id)
            if existing:
                # Update existing
                analysis.id = existing.id
                return await self.update(existing.id, analysis)
            else:
                # Create new
                analysis.call_id = call_id
                return await self.create(analysis)
        except Exception as e:
            logger.error(f"Error upserting analysis: {e}")
            raise e
    
    def _to_domain(self, orm_obj: CallAnalysisORM) -> CallAnalysis:
        """
        Convert ORM model to domain model.
        
        Handles string-to-enum conversion when reading from database.
        Pydantic will handle most conversions, but we ensure enums are properly converted.
        """
        # Use base conversion first
        domain_obj = super()._to_domain(orm_obj)
        
        # The base method uses model_validate which should handle enum conversion
        # But we can add explicit conversion if needed for safety
        # Pydantic should automatically convert strings to enums based on field types
        
        return domain_obj
    
    def _to_orm(self, domain_obj: CallAnalysis) -> CallAnalysisORM:
        """
        Convert domain model to ORM model.
        
        Handles enum-to-string conversion for database storage.
        """
        data = domain_obj.model_dump(exclude={"id"} if domain_obj.id else set())
        
        # Convert enums to strings for database storage
        if "status" in data and isinstance(data["status"], AnalysisStatus):
            data["status"] = data["status"].value
        
        if "objections" in data and data["objections"]:
            data["objections"] = [
                obj.value if isinstance(obj, ObjectionType) else str(obj)
                for obj in data["objections"]
            ]
        
        if "sop_stages_completed" in data and data["sop_stages_completed"]:
            data["sop_stages_completed"] = [
                stage.value if isinstance(stage, SOPStage) else str(stage)
                for stage in data["sop_stages_completed"]
            ]
        
        if "sop_stages_missed" in data and data["sop_stages_missed"]:
            data["sop_stages_missed"] = [
                stage.value if isinstance(stage, SOPStage) else str(stage)
                for stage in data["sop_stages_missed"]
            ]
        
        return self.orm_model(**data)

