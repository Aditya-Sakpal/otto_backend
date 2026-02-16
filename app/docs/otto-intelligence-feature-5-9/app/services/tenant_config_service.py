"""
Tenant Configuration Service

Provides:
- Retrieval and caching of tenant configurations
- Application of tenant-specific rules during extraction
- Default configuration fallback
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.tenant_config import (
    TenantConfiguration,
    QualificationThresholds,
    QualificationRule,
    ServiceConfig,
    ServicePrioritization,
    CustomKeywords,
    BusinessHours,
    PropertyDetailsConfig,
    get_default_tenant_config
)
from ..models.enums import ServicePriority, QualificationStatus

logger = logging.getLogger(__name__)


class TenantConfigService:
    """
    Service for managing and applying tenant configurations.
    
    Features:
    - Caching with TTL for performance
    - Default config fallback
    - Qualification rule evaluation
    - Service prioritization
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.tenant_configurations
        self._cache: Dict[str, Tuple[TenantConfiguration, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
    
    async def get_config(self, company_id: str) -> TenantConfiguration:
        """
        Get tenant configuration with caching.
        
        Args:
            company_id: Company/tenant identifier
            
        Returns:
            TenantConfiguration for the company, or default if none exists
        """
        # Check cache first
        if company_id in self._cache:
            config, cached_at = self._cache[company_id]
            if datetime.utcnow() - cached_at < self._cache_ttl:
                return config
        
        # Fetch from database
        config_doc = await self.collection.find_one({
            "company_id": company_id,
            "is_active": True
        })
        
        if not config_doc:
            # Return default configuration
            config = get_default_tenant_config(company_id)
            logger.debug(f"No tenant config found for {company_id}, using default")
        else:
            # Remove MongoDB _id field
            config_doc.pop("_id", None)
            config = TenantConfiguration(**config_doc)
            logger.debug(f"Loaded tenant config for {company_id} (version {config.version})")
        
        # Cache it
        self._cache[company_id] = (config, datetime.utcnow())
        
        return config
    
    async def create_config(
        self, 
        company_id: str, 
        company_name: str,
        **kwargs
    ) -> TenantConfiguration:
        """
        Create a new tenant configuration.
        
        Args:
            company_id: Company/tenant identifier
            company_name: Display name of the company
            **kwargs: Additional configuration fields
            
        Returns:
            Created TenantConfiguration
        """
        # Check if config already exists
        existing = await self.collection.find_one({"company_id": company_id})
        if existing:
            raise ValueError(f"Configuration for company {company_id} already exists")
        
        config = TenantConfiguration(
            config_id=f"config_{uuid.uuid4().hex[:12]}",
            company_id=company_id,
            company_name=company_name,
            **kwargs
        )
        
        await self.collection.insert_one(config.model_dump())
        
        # Invalidate cache
        self._cache.pop(company_id, None)
        
        logger.info(f"Created tenant config for {company_id}")
        return config
    
    async def update_config(
        self, 
        company_id: str, 
        updates: Dict[str, Any],
        updated_by: Optional[str] = None
    ) -> Optional[TenantConfiguration]:
        """
        Update an existing tenant configuration.
        
        Args:
            company_id: Company/tenant identifier
            updates: Fields to update
            updated_by: User who made the update
            
        Returns:
            Updated TenantConfiguration, or None if not found
        """
        # Get current config
        current = await self.collection.find_one({"company_id": company_id})
        if not current:
            return None
        
        # Archive current version
        current["_archived_at"] = datetime.utcnow()
        await self.db.tenant_configurations_history.insert_one(current)
        
        # Prepare update
        updates["updated_at"] = datetime.utcnow()
        updates["version"] = current.get("version", 0) + 1
        if updated_by:
            updates["updated_by"] = updated_by
        
        # Update
        await self.collection.update_one(
            {"company_id": company_id},
            {"$set": updates}
        )
        
        # Invalidate cache
        self._cache.pop(company_id, None)
        
        # Fetch and return updated config
        updated = await self.collection.find_one({"company_id": company_id})
        updated.pop("_id", None)
        
        logger.info(f"Updated tenant config for {company_id} (version {updates['version']})")
        return TenantConfiguration(**updated)
    
    async def delete_config(self, company_id: str) -> bool:
        """
        Delete a tenant configuration (soft delete - mark as inactive).
        
        Args:
            company_id: Company/tenant identifier
            
        Returns:
            True if deleted, False if not found
        """
        result = await self.collection.update_one(
            {"company_id": company_id},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
        )
        
        # Invalidate cache
        self._cache.pop(company_id, None)
        
        return result.modified_count > 0
    
    def invalidate_cache(self, company_id: Optional[str] = None):
        """
        Invalidate cached configuration.
        
        Args:
            company_id: Specific company to invalidate, or None for all
        """
        if company_id:
            self._cache.pop(company_id, None)
        else:
            self._cache.clear()
    
    def apply_qualification_rules(
        self, 
        extracted: Dict[str, Any], 
        config: TenantConfiguration
    ) -> Dict[str, Any]:
        """
        Apply tenant-specific qualification rules to extracted data.
        
        Args:
            extracted: Extracted qualification data
            config: Tenant configuration
            
        Returns:
            Modified extraction result with tenant rules applied
        """
        # Apply custom thresholds
        thresholds = config.qualification_thresholds
        overall_score = extracted.get("overall_score", 0.0)
        
        # Calculate qualification status from custom thresholds
        if overall_score >= thresholds.hot_min_score:
            extracted["qualification_status"] = "hot"
        elif overall_score >= thresholds.warm_min_score:
            extracted["qualification_status"] = "warm"
        elif overall_score >= thresholds.cold_min_score:
            extracted["qualification_status"] = "cold"
        else:
            extracted["qualification_status"] = "unqualified"
        
        # Apply service prioritization
        service = (extracted.get("service_requested") or "").lower()
        service_config = self._get_service_config(service, config)
        
        if service_config:
            # Check if service is deprioritized
            if service_config.priority == ServicePriority.DEFERRED:
                extracted["is_deprioritized"] = True
                extracted["service_wait_time_weeks"] = service_config.current_wait_time_weeks
                extracted["deprioritization_note"] = service_config.notes
            elif service_config.priority == ServicePriority.NOT_OFFERED:
                extracted["service_not_offered"] = True
            
            # Apply service-specific score adjustment
            if service_config.qualification_boost != 0:
                extracted["overall_score"] = min(1.0, max(0.0, 
                    overall_score + service_config.qualification_boost
                ))
        
        # Apply custom qualification rules
        for rule in sorted(config.qualification_rules, key=lambda r: -r.priority):
            if rule.enabled and self._evaluate_rule(extracted, rule):
                extracted = self._apply_rule_action(extracted, rule)
        
        return extracted
    
    def _get_service_config(
        self, 
        service: str, 
        config: TenantConfiguration
    ) -> Optional[ServiceConfig]:
        """Find service configuration by service type."""
        service_lower = service.lower()
        
        for svc in config.service_prioritization.services:
            # Check exact match
            if svc.service_type.lower() == service_lower:
                return svc
            
            # Check keywords
            keywords = config.custom_keywords.service_keywords.get(svc.service_type, [])
            if any(kw.lower() in service_lower for kw in keywords):
                return svc
        
        return None
    
    def _evaluate_rule(self, extracted: Dict[str, Any], rule: QualificationRule) -> bool:
        """
        Safely evaluate a qualification rule condition.
        
        Uses a restricted eval context to prevent code injection.
        """
        try:
            # Create safe evaluation context
            bant_scores = extracted.get("bant_scores", {})
            context = {
                "bant_scores": bant_scores,
                "need": bant_scores.get("need", 0.0),
                "budget": bant_scores.get("budget", 0.0),
                "authority": bant_scores.get("authority", 0.0),
                "timeline": bant_scores.get("timeline", 0.0),
                "urgency_signals": " ".join(str(s) for s in extracted.get("urgency_signals", []) if s).lower(),
                "budget_indicators": " ".join(str(b) for b in extracted.get("budget_indicators", []) if b).lower(),
                "overall_score": extracted.get("overall_score", 0.0),
                "service_requested": (extracted.get("service_requested") or "").lower(),
                "qualification_status": extracted.get("qualification_status", ""),
            }
            
            # Use safe eval with limited scope
            return eval(rule.condition, {"__builtins__": {}}, context)
            
        except Exception as e:
            logger.warning(f"Rule evaluation failed: {rule.rule_id}: {e}")
            return False
    
    def _apply_rule_action(
        self, 
        extracted: Dict[str, Any], 
        rule: QualificationRule
    ) -> Dict[str, Any]:
        """Apply the action from a matched rule."""
        action = rule.action
        value = rule.action_value
        
        if action == "boost_score":
            current = extracted.get("overall_score", 0.0)
            extracted["overall_score"] = min(1.0, current + float(value))
            logger.debug(f"Rule {rule.rule_id}: boosted score by {value}")
            
        elif action == "reduce_score":
            current = extracted.get("overall_score", 0.0)
            extracted["overall_score"] = max(0.0, current - float(value))
            logger.debug(f"Rule {rule.rule_id}: reduced score by {value}")
            
        elif action == "set_status":
            extracted["qualification_status"] = value
            logger.debug(f"Rule {rule.rule_id}: set status to {value}")
            
        elif action == "set_priority":
            extracted["custom_priority"] = value
            logger.debug(f"Rule {rule.rule_id}: set priority to {value}")
            
        elif action == "flag":
            flags = extracted.get("flags", [])
            flags.append(value)
            extracted["flags"] = flags
            logger.debug(f"Rule {rule.rule_id}: added flag {value}")
        
        # Track which rules were applied
        applied_rules = extracted.get("applied_rules", [])
        applied_rules.append(rule.rule_id)
        extracted["applied_rules"] = applied_rules
        
        return extracted
    
    def get_custom_keywords_context(self, config: TenantConfiguration) -> str:
        """
        Build a prompt context string from custom keywords.
        
        Used to inject tenant-specific keywords into extraction prompts.
        """
        keywords = config.custom_keywords
        context_parts = []
        
        if keywords.urgency_keywords:
            context_parts.append("\n**TENANT-SPECIFIC URGENCY INDICATORS:**")
            for cat in keywords.urgency_keywords:
                all_terms = cat.keywords + cat.phrases
                if all_terms:
                    context_parts.append(f"- {', '.join(all_terms)} → {cat.effect}")
        
        if keywords.budget_keywords:
            context_parts.append("\n**TENANT-SPECIFIC BUDGET INDICATORS:**")
            for cat in keywords.budget_keywords:
                all_terms = cat.keywords + cat.phrases
                if all_terms:
                    context_parts.append(f"- {', '.join(all_terms)} → {cat.effect}")
        
        if keywords.service_keywords:
            context_parts.append("\n**SERVICE TYPE KEYWORDS:**")
            for service, kws in keywords.service_keywords.items():
                if kws:
                    context_parts.append(f"- {service}: {', '.join(kws)}")
        
        return "\n".join(context_parts) if context_parts else ""


# Singleton instance holder
_tenant_config_service: Optional[TenantConfigService] = None


def get_tenant_config_service(db: AsyncIOMotorDatabase) -> TenantConfigService:
    """
    Get tenant config service instance.
    
    Note: This creates a new instance if db changes. For true singleton
    behavior in the app, use dependency injection.
    """
    global _tenant_config_service
    if _tenant_config_service is None or _tenant_config_service.db != db:
        _tenant_config_service = TenantConfigService(db)
    return _tenant_config_service

