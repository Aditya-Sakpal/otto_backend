"""
SOP Document Service

Handles SOP document upload, storage, and retrieval.
"""

import logging
import hashlib
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings
from app.models.sop import (
    SOPDocument, SOPMetricsDocument, SOPChunk, SOPFileInfo,
    ProcessingMetadata, ExtractedContent
)
from app.models.enums import SOPType, SOPStatus


logger = logging.getLogger(__name__)


class DocumentService:
    """Service for SOP document management"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize document service"""
        self.db = db
        self.sop_documents = db.sop_documents
        self.sop_metrics = db.sop_metrics
        self.sop_chunks = db.sop_chunks
    
    async def create_sop_document(
        self,
        company_id: str,
        sop_name: str,
        file_bytes: bytes,
        filename: str,
        file_type: str,
        target_role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create SOP document entry in database.
        
        Args:
            company_id: Company identifier
            sop_name: SOP document name
            file_bytes: File content
            filename: Original filename
            file_type: MIME type
            target_role: Target role (None for company-wide)
            metadata: Additional metadata
            
        Returns:
            sop_id: Generated SOP document ID
        """
        # Generate IDs
        sop_id = f"sop_{uuid.uuid4().hex[:12]}"
        
        # Calculate file hash
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # Create file info
        file_info = SOPFileInfo(
            original_filename=filename,
            file_type=file_type,
            file_size=len(file_bytes),
            file_hash=f"sha256:{file_hash}",
            s3_key=None,  # TODO: Implement S3 upload if needed
            page_count=None,
            word_count=None
        )
        
        # Create document
        # Get version from metadata if provided, otherwise use default (1)
        version = 1
        if metadata and metadata.get("version") is not None:
            version = metadata.get("version")
        
        sop_doc = SOPDocument(
            sop_id=sop_id,
            company_id=company_id,
            sop_name=sop_name,
            sop_type=SOPType.GENERAL_SOP,  # Will be updated during validation
            target_role=target_role,
            is_company_wide=target_role is None,
            version=version,
            status=SOPStatus.PROCESSING,
            file_info=file_info,
            metadata=metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Insert to database
        await self.sop_documents.insert_one(sop_doc.model_dump(by_alias=True))
        
        logger.info(f"Created SOP document: {sop_id} for company {company_id}")
        
        return sop_id
    
    async def update_sop_document(
        self,
        sop_id: str,
        update_data: Dict[str, Any]
    ) -> bool:
        """
        Update SOP document fields.
        
        Args:
            sop_id: SOP document ID
            update_data: Fields to update
            
        Returns:
            Success status
        """
        update_data["updated_at"] = datetime.utcnow()
        
        result = await self.sop_documents.update_one(
            {"sop_id": sop_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    async def get_sop_document(self, sop_id: str) -> Optional[Dict[str, Any]]:
        """Get SOP document by ID"""
        return await self.sop_documents.find_one({"sop_id": sop_id})
    
    async def get_company_sops(
        self,
        company_id: str,
        status: Optional[SOPStatus] = None,
        target_role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all SOP documents for a company"""
        query: Dict[str, Any] = {"company_id": company_id}
        
        if status:
            query["status"] = status.value
        
        if target_role:
            query["$or"] = [
                {"target_role": target_role},
                {"is_company_wide": True}
            ]
        
        cursor = self.sop_documents.find(query).sort("created_at", -1)
        return await cursor.to_list(length=100)
    
    async def save_metrics(
        self,
        sop_id: str,
        company_id: str,
        metrics: List[Dict[str, Any]],
        target_role: Optional[str] = None,
        is_company_wide: bool = False
    ) -> bool:
        """
        Save extracted metrics.
        
        Also deactivates other SOPs for the same company/role to prevent
        ambiguity in which SOP is used for compliance checking.
        
        Args:
            sop_id: SOP document ID
            company_id: Company identifier
            metrics: List of extracted metrics
            target_role: Target role
            is_company_wide: Company-wide flag
            
        Returns:
            Success status
        """
        # Deactivate other SOPs for the same company/role to prevent ambiguity
        # This ensures only ONE SOP is active per company/role combination
        deactivate_query = {
            "company_id": company_id,
            "sop_id": {"$ne": sop_id},  # Don't deactivate the one we're saving
            "status": SOPStatus.ACTIVE.value
        }
        
        if target_role:
            deactivate_query["target_role"] = target_role
        elif is_company_wide:
            deactivate_query["is_company_wide"] = True
        
        deactivated = await self.sop_metrics.update_many(
            deactivate_query,
            {"$set": {"status": SOPStatus.INACTIVE.value, "updated_at": datetime.utcnow()}}
        )
        
        if deactivated.modified_count > 0:
            logger.info(
                f"Deactivated {deactivated.modified_count} previous SOP(s) for "
                f"company={company_id}, role={target_role or 'company-wide'} "
                f"to prevent ambiguity"
            )
        
        # Calculate total weight
        total_weight = sum(m.get("weight", 0.1) for m in metrics)
        
        # Extract categories
        categories = list(set(m.get("category", "general") for m in metrics if m.get("category")))
        
        # Create metrics document
        metrics_doc = SOPMetricsDocument(
            sop_id=sop_id,
            company_id=company_id,
            target_role=target_role,
            is_company_wide=is_company_wide,
            status=SOPStatus.ACTIVE,
            metrics=metrics,
            total_metrics=len(metrics),
            total_weight=total_weight,
            categories=categories,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Upsert to database
        await self.sop_metrics.replace_one(
            {"sop_id": sop_id},
            metrics_doc.model_dump(by_alias=True),
            upsert=True
        )
        
        logger.info(
            f"Saved {len(metrics)} metrics for SOP {sop_id} "
            f"(company={company_id}, role={target_role or 'company-wide'})"
        )
        
        return True
    
    async def get_sop_metrics(
        self,
        company_id: str,
        target_role: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get active SOP metrics for company/role.
        
        Priority:
        1. Role-specific SOP for the given role
        2. Company-wide SOP (is_company_wide=True)
        
        Sorting:
        - Uses most recently updated SOP if multiple match
        - Logs which SOP is being used for traceability
        """
        query: Dict[str, Any] = {
            "company_id": company_id,
            "status": SOPStatus.ACTIVE.value
        }
        
        # Try role-specific first
        if target_role:
            role_query = query.copy()
            role_query["target_role"] = target_role
            # Sort by updated_at DESC to get most recent if multiple exist
            role_sop = await self.sop_metrics.find_one(
                role_query, 
                sort=[("updated_at", -1)]
            )
            if role_sop:
                # Enrich with version info from sop_documents
                sop_doc = await self.sop_documents.find_one({"sop_id": role_sop.get("sop_id")})
                if sop_doc:
                    role_sop["sop_version"] = sop_doc.get("version", 1)
                    role_sop["sop_name"] = sop_doc.get("sop_name")
                    role_sop["version_history_id"] = sop_doc.get("version_history_id")
                
                logger.info(
                    f"Using role-specific SOP for compliance: "
                    f"sop_id={role_sop.get('sop_id')}, "
                    f"version={role_sop.get('sop_version', 'unknown')}, "
                    f"role={target_role}, "
                    f"metrics_count={role_sop.get('total_metrics', 0)}"
                )
                return role_sop
        
        # Fall back to company-wide
        company_query = query.copy()
        company_query["is_company_wide"] = True
        # Sort by updated_at DESC to get most recent if multiple exist
        company_sop = await self.sop_metrics.find_one(
            company_query,
            sort=[("updated_at", -1)]
        )
        
        if company_sop:
            # Enrich with version info from sop_documents
            sop_doc = await self.sop_documents.find_one({"sop_id": company_sop.get("sop_id")})
            if sop_doc:
                company_sop["sop_version"] = sop_doc.get("version", 1)
                company_sop["sop_name"] = sop_doc.get("sop_name")
                company_sop["version_history_id"] = sop_doc.get("version_history_id")
            
            logger.info(
                f"Using company-wide SOP for compliance: "
                f"sop_id={company_sop.get('sop_id')}, "
                f"version={company_sop.get('sop_version', 'unknown')}, "
                f"metrics_count={company_sop.get('total_metrics', 0)}"
            )
        else:
            logger.warning(
                f"No active SOP found for company {company_id} "
                f"(role={target_role}). Compliance check will use generic evaluation."
            )
        
        return company_sop
    
    async def save_chunks(self, chunks: List[SOPChunk]) -> bool:
        """Save SOP chunks to database"""
        if not chunks:
            return False
        
        # Convert to dicts
        chunk_dicts = [chunk.model_dump(by_alias=True) for chunk in chunks]
        
        # Bulk insert
        await self.sop_chunks.insert_many(chunk_dicts)
        
        logger.info(f"Saved {len(chunks)} chunks")
        
        return True
    
    async def get_chunks(self, sop_id: str) -> List[Dict[str, Any]]:
        """Get all chunks for SOP"""
        cursor = self.sop_chunks.find({"sop_id": sop_id}).sort("chunk_index", 1)
        return await cursor.to_list(length=1000)
    
    async def update_sop_status(
        self,
        sop_id: str,
        status: SOPStatus,
        reason: Optional[str] = None
    ) -> bool:
        """Update SOP document status"""
        update_data = {
            "status": status.value,
            "updated_at": datetime.utcnow()
        }
        
        result = await self.sop_documents.update_one(
            {"sop_id": sop_id},
            {"$set": update_data}
        )
        
        # Also update metrics status
        if status in [SOPStatus.ACTIVE, SOPStatus.INACTIVE]:
            await self.sop_metrics.update_one(
                {"sop_id": sop_id},
                {"$set": {"status": status.value, "updated_at": datetime.utcnow()}}
            )
        
        logger.info(f"Updated SOP {sop_id} status to {status.value}")
        
        return result.modified_count > 0
    
    async def delete_sop(self, sop_id: str) -> bool:
        """Delete SOP document and all related data"""
        # Delete document
        await self.sop_documents.delete_one({"sop_id": sop_id})
        
        # Delete metrics
        await self.sop_metrics.delete_one({"sop_id": sop_id})
        
        # Delete chunks
        await self.sop_chunks.delete_many({"sop_id": sop_id})
        
        logger.info(f"Deleted SOP {sop_id} and related data")
        
        return True
    
    async def list_sops(
        self,
        company_id: str,
        status: Optional[str] = None,
        target_role: Optional[str] = None,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """List SOP documents with pagination"""
        query: Dict[str, Any] = {"company_id": company_id}
        
        if status:
            query["status"] = status
        
        if target_role:
            query["$or"] = [
                {"target_role": target_role},
                {"is_company_wide": True}
            ]
        
        # Count total
        total = await self.sop_documents.count_documents(query)
        
        # Get page
        skip = (page - 1) * limit
        cursor = self.sop_documents.find(query).sort("created_at", -1).skip(skip).limit(limit)
        documents = await cursor.to_list(length=limit)
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "documents": documents
        }

