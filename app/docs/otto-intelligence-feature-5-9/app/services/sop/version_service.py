"""
SOP Version Service

Handles SOP versioning logic including:
- Creating new versions (per Q1: automatic version numbers)
- Archiving old versions (per Q2: immediate archival)
- Scheduled activation (per Q4: activation_date support)
- Version history retrieval

Based on manager decisions Q1-Q9.
"""

import logging
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.sop import (
    SOPDocument, SOPVersionHistory, SOPMetric, SOPMetricsDocument
)
from app.models.enums import SOPStatus


logger = logging.getLogger(__name__)


class SOPVersionService:
    """Handle SOP versioning logic"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.sop_documents = db.sop_documents
        self.sop_metrics = db.sop_metrics
        self.sop_version_history = db.sop_version_history
    
    async def create_new_version(
        self,
        company_id: str,
        sop_id: str,
        file_bytes: bytes,
        filename: str,
        metrics: List[SOPMetric],
        sop_name: str,
        activation_date: Optional[datetime] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create new SOP version (per Q1-Q4 decisions).
        
        Process:
        1. Archive current active version
        2. Create new version record in history
        3. Extract metrics from new document (done by caller)
        4. Set activation (immediate or scheduled)
        
        Args:
            company_id: Company identifier
            sop_id: SOP document ID
            file_bytes: New document content
            filename: Original filename
            metrics: Extracted metrics from new document
            sop_name: SOP name
            activation_date: Optional scheduled activation (None = immediate)
            created_by: Manager who uploaded
            
        Returns:
            Dict with version info including history_id
        """
        # Calculate file hash to detect duplicates
        file_hash = f"sha256:{hashlib.sha256(file_bytes).hexdigest()}"
        
        # Get current version (if any)
        current_sop = await self.sop_documents.find_one({"sop_id": sop_id})
        
        if current_sop:
            current_version = current_sop.get("version", 1)
            
            # Check if current version has a history record (may not exist for legacy SOPs)
            existing_history = await self.sop_version_history.find_one({
                "sop_id": sop_id,
                "version": current_version,
                "status": "active"
            })
            
            if not existing_history:
                # Create history record for the current version before archiving
                # This handles legacy SOPs created before version history was implemented
                logger.info(f"Creating missing history record for version {current_version} of SOP {sop_id}")
                
                # Get current metrics to snapshot
                current_metrics = await self.sop_metrics.find_one({"sop_id": sop_id})
                metrics_snapshot = current_metrics.get("metrics", []) if current_metrics else []
                
                legacy_history = SOPVersionHistory(
                    history_id=f"sop_hist_{uuid.uuid4().hex[:12]}",
                    sop_id=sop_id,
                    company_id=current_sop.get("company_id"),
                    version=current_version,
                    sop_name=current_sop.get("sop_name", ""),
                    created_at=current_sop.get("created_at", datetime.utcnow()),
                    created_by=None,
                    activation_date=current_sop.get("activation_date") or current_sop.get("created_at", datetime.utcnow()),
                    archived_at=None,
                    status="active",
                    metrics_snapshot=metrics_snapshot,
                    total_metrics=len(metrics_snapshot),
                    total_weight=sum(m.get("weight", 0.1) for m in metrics_snapshot),
                    file_hash=current_sop.get("file_info", {}).get("file_hash", ""),
                    original_filename=current_sop.get("file_info", {}).get("original_filename", "")
                )
                
                await self.sop_version_history.insert_one(legacy_history.model_dump(by_alias=True))
            
            # Now archive current version
            await self._archive_current_version(sop_id)
            new_version = current_version + 1
        else:
            new_version = 1
        
        # Generate history ID
        history_id = f"sop_hist_{uuid.uuid4().hex[:12]}"
        
        # Determine initial status
        if activation_date and activation_date > datetime.utcnow():
            status = "scheduled"
        else:
            status = "active"
            activation_date = datetime.utcnow()
        
        # Create version history record
        history_record = SOPVersionHistory(
            history_id=history_id,
            sop_id=sop_id,
            company_id=company_id,
            version=new_version,
            sop_name=sop_name,
            created_at=datetime.utcnow(),
            created_by=created_by,
            activation_date=activation_date,
            archived_at=None,
            status=status,
            metrics_snapshot=[m.model_dump() if hasattr(m, 'model_dump') else m for m in metrics],
            total_metrics=len(metrics),
            total_weight=sum(m.weight if hasattr(m, 'weight') else m.get('weight', 0.1) for m in metrics),
            file_hash=file_hash,
            original_filename=filename
        )
        
        # Store version history
        await self.sop_version_history.insert_one(history_record.model_dump(by_alias=True))
        
        logger.info(f"Created SOP version {new_version} for {sop_id} (history_id: {history_id}, status: {status})")
        
        return {
            "version": new_version,
            "history_id": history_id,
            "status": status,
            "activation_date": activation_date,
            "file_hash": file_hash
        }
    
    async def _archive_current_version(self, sop_id: str) -> None:
        """
        Archive the current active version (per Q2: immediate archival).
        
        Updates:
        - sop_version_history: Set status='archived', archived_at=now
        - sop_metrics: Set status='inactive'
        """
        now = datetime.utcnow()
        
        # Archive in version history
        await self.sop_version_history.update_many(
            {"sop_id": sop_id, "status": "active"},
            {
                "$set": {
                    "status": "archived",
                    "archived_at": now
                }
            }
        )
        
        # Deactivate current metrics (keep for reference)
        await self.sop_metrics.update_many(
            {"sop_id": sop_id, "status": SOPStatus.ACTIVE.value},
            {"$set": {"status": SOPStatus.INACTIVE.value, "updated_at": now}}
        )
        
        logger.info(f"Archived current version for SOP {sop_id}")
    
    async def get_version_history(
        self,
        sop_id: str,
        include_archived: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all versions for an SOP.
        
        Args:
            sop_id: SOP document ID
            include_archived: Whether to include archived versions
            
        Returns:
            List of version history records sorted by version desc
        """
        query = {"sop_id": sop_id}
        
        if not include_archived:
            query["status"] = {"$ne": "archived"}
        
        cursor = self.sop_version_history.find(query).sort("version", -1)
        versions = await cursor.to_list(length=100)
        
        # Remove MongoDB _id
        for v in versions:
            v.pop("_id", None)
        
        return versions
    
    async def get_specific_version(
        self,
        sop_id: str,
        version: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific version details.
        
        Args:
            sop_id: SOP document ID
            version: Version number to retrieve
            
        Returns:
            Version history record or None
        """
        record = await self.sop_version_history.find_one({
            "sop_id": sop_id,
            "version": version
        })
        
        if record:
            record.pop("_id", None)
        
        return record
    
    async def get_active_version(
        self,
        sop_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the currently active version for an SOP."""
        record = await self.sop_version_history.find_one({
            "sop_id": sop_id,
            "status": "active"
        })
        
        if record:
            record.pop("_id", None)
        
        return record
    
    async def get_active_version_at_time(
        self,
        sop_id: str,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Get which version was active at a specific time.
        
        Useful for historical analysis to know which SOP version
        was in effect when a call was evaluated.
        
        Args:
            sop_id: SOP document ID
            timestamp: Point in time to check
            
        Returns:
            Version history record that was active at that time
        """
        # Find version that was:
        # 1. Created before the timestamp
        # 2. Either still active OR archived after the timestamp
        record = await self.sop_version_history.find_one(
            {
                "sop_id": sop_id,
                "activation_date": {"$lte": timestamp},
                "$or": [
                    {"status": "active"},
                    {"archived_at": {"$gt": timestamp}},
                    {"archived_at": None}
                ]
            },
            sort=[("version", -1)]
        )
        
        if record:
            record.pop("_id", None)
        
        return record
    
    async def schedule_activation(
        self,
        version_history_id: str,
        activation_date: datetime
    ) -> bool:
        """
        Schedule a version for future activation (per Q4).
        
        Args:
            version_history_id: Version history record ID
            activation_date: When to activate
            
        Returns:
            Success status
        """
        if activation_date <= datetime.utcnow():
            raise ValueError("Activation date must be in the future")
        
        result = await self.sop_version_history.update_one(
            {"history_id": version_history_id, "status": "scheduled"},
            {
                "$set": {
                    "activation_date": activation_date
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Scheduled activation for {version_history_id} at {activation_date}")
            return True
        
        return False
    
    async def activate_scheduled_version(
        self,
        version_history_id: str
    ) -> bool:
        """
        Activate a scheduled version (called by background job).
        
        Process:
        1. Archive current active version
        2. Set scheduled version to active
        3. Update main SOP document
        4. Update metrics status
        """
        # Get the scheduled version
        scheduled = await self.sop_version_history.find_one({
            "history_id": version_history_id,
            "status": "scheduled"
        })
        
        if not scheduled:
            logger.warning(f"Scheduled version {version_history_id} not found")
            return False
        
        sop_id = scheduled["sop_id"]
        company_id = scheduled["company_id"]
        
        # Archive current active version
        await self._archive_current_version(sop_id)
        
        # Activate the scheduled version
        now = datetime.utcnow()
        await self.sop_version_history.update_one(
            {"history_id": version_history_id},
            {
                "$set": {
                    "status": "active",
                    "activation_date": now
                }
            }
        )
        
        # Update main SOP document
        await self.sop_documents.update_one(
            {"sop_id": sop_id},
            {
                "$set": {
                    "version": scheduled["version"],
                    "version_history_id": version_history_id,
                    "activation_date": now,
                    "updated_at": now
                }
            }
        )
        
        # Update metrics to active (create from snapshot)
        metrics_snapshot = scheduled.get("metrics_snapshot", [])
        if metrics_snapshot:
            metrics_doc = SOPMetricsDocument(
                sop_id=sop_id,
                company_id=company_id,
                target_role=scheduled.get("target_role"),
                is_company_wide=scheduled.get("is_company_wide", False),
                status=SOPStatus.ACTIVE,
                metrics=metrics_snapshot,
                total_metrics=len(metrics_snapshot),
                total_weight=sum(m.get("weight", 0.1) for m in metrics_snapshot),
                categories=list(set(m.get("category", "general") for m in metrics_snapshot)),
                created_at=now,
                updated_at=now
            )
            
            await self.sop_metrics.replace_one(
                {"sop_id": sop_id},
                metrics_doc.model_dump(by_alias=True),
                upsert=True
            )
        
        logger.info(f"Activated scheduled version {version_history_id} for SOP {sop_id}")
        return True
    
    async def check_for_duplicate(
        self,
        sop_id: str,
        file_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a file with the same hash has already been uploaded.
        
        Used to prevent duplicate uploads and warn users.
        
        Args:
            sop_id: SOP document ID
            file_hash: SHA256 hash of file content
            
        Returns:
            Existing version record if duplicate found, None otherwise
        """
        record = await self.sop_version_history.find_one({
            "sop_id": sop_id,
            "file_hash": file_hash
        })
        
        if record:
            record.pop("_id", None)
        
        return record
    
    async def get_version_comparison(
        self,
        sop_id: str,
        version_a: int,
        version_b: int
    ) -> Dict[str, Any]:
        """
        Compare two versions of an SOP (per Q9: pin for later - basic support).
        
        Returns a comparison of metrics between two versions.
        
        Args:
            sop_id: SOP document ID
            version_a: First version
            version_b: Second version
            
        Returns:
            Comparison dict with added, removed, and changed metrics
        """
        version_a_doc = await self.get_specific_version(sop_id, version_a)
        version_b_doc = await self.get_specific_version(sop_id, version_b)
        
        if not version_a_doc or not version_b_doc:
            raise ValueError(f"Version not found")
        
        metrics_a = {m["metric_id"]: m for m in version_a_doc.get("metrics_snapshot", [])}
        metrics_b = {m["metric_id"]: m for m in version_b_doc.get("metrics_snapshot", [])}
        
        ids_a = set(metrics_a.keys())
        ids_b = set(metrics_b.keys())
        
        added = list(ids_b - ids_a)
        removed = list(ids_a - ids_b)
        common = ids_a & ids_b
        
        # Check for changes in common metrics
        changed = []
        for metric_id in common:
            a = metrics_a[metric_id]
            b = metrics_b[metric_id]
            
            if a.get("weight") != b.get("weight") or a.get("target_value") != b.get("target_value"):
                changed.append({
                    "metric_id": metric_id,
                    "metric_name": b.get("metric_name"),
                    "old_weight": a.get("weight"),
                    "new_weight": b.get("weight"),
                    "old_target": a.get("target_value"),
                    "new_target": b.get("target_value")
                })
        
        return {
            "sop_id": sop_id,
            "version_a": version_a,
            "version_b": version_b,
            "metrics_added": len(added),
            "metrics_removed": len(removed),
            "metrics_changed": len(changed),
            "added_metric_ids": added,
            "removed_metric_ids": removed,
            "changed_metrics": changed
        }


# Singleton
_version_service: Optional[SOPVersionService] = None


def get_version_service(db: AsyncIOMotorDatabase) -> SOPVersionService:
    """Get SOPVersionService instance"""
    global _version_service
    if _version_service is None:
        _version_service = SOPVersionService(db)
    return _version_service
