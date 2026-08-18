"""
Tenant Configuration Service.

Handles creating/retrieving tenant configs by:
1. Calling the Shunya tenant-config API
2. Storing the config locally in PostgreSQL
"""
import traceback
from typing import Optional, Dict, Any
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.models.tenant_config import TenantConfigORM

logger = get_logger(__name__)


class TenantConfigService:
    """Service for tenant configuration management."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.base_url = settings.UWC_BASE_URL.rstrip("/")
        self.api_key = settings.API_KEY or settings.UWC_API_KEY or settings.UWC_JWT_SECRET

    @staticmethod
    def _normalize_shunya_priority(priority: str | None) -> str:
        """
        Normalize local priority values to Shoonya's enum.

        Shoonya expects: urgent | high | normal | deferred | not_offered
        """
        p = (priority or "normal").strip().lower()
        if p in {"urgent", "high", "normal", "deferred", "not_offered"}:
            return p
        # Local schemas historically used LOW; map to deferred for compatibility.
        if p in {"low", "lowest"}:
            return "deferred"
        return "normal"

    @classmethod
    def _to_shunya_qualification_thresholds(
        cls,
        qt: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Translate Otto's local qualification_thresholds to Shoonya's expected shape.

        Otto local:  hot_threshold, warm_threshold, cold_threshold,
                     scoring_weights: {need, budget, authority, timeline}
        Shoonya:     hot_min_score, warm_min_score, cold_min_score,
                     need_weight, budget_weight, authority_weight, timeline_weight
        """
        if not qt or not isinstance(qt, dict):
            return qt

        result = dict(qt)

        # Rename threshold fields
        for local, shunya in (
            ("hot_threshold", "hot_min_score"),
            ("warm_threshold", "warm_min_score"),
            ("cold_threshold", "cold_min_score"),
        ):
            if local in result and shunya not in result:
                result[shunya] = result.pop(local)

        # Flatten scoring_weights into top-level weight fields
        weights = result.pop("scoring_weights", None)
        if isinstance(weights, dict):
            for dim in ("need", "budget", "authority", "timeline"):
                key = f"{dim}_weight"
                if dim in weights and key not in result:
                    result[key] = weights[dim]

        return result

    @classmethod
    def _to_shunya_business_hours(
        cls,
        bh: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Translate Otto's per-day business_hours to Shoonya's flat shape.

        Otto local:  {timezone, monday: {open, close, is_closed}, ..., saturday: {...}, sunday: {...}}
        Shoonya:     {timezone, weekday_start, weekday_end,
                      saturday_start, saturday_end, sunday_closed, holidays}
        """
        if not bh or not isinstance(bh, dict):
            return bh

        # If it already uses Shoonya's flat format, pass through as-is.
        if "weekday_start" in bh or "weekday_end" in bh:
            return bh

        result: Dict[str, Any] = {"timezone": bh.get("timezone", "America/Phoenix")}

        # Derive weekday hours from the first available weekday entry.
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
            sched = bh.get(day)
            if isinstance(sched, dict) and not sched.get("is_closed"):
                result["weekday_start"] = sched.get("open", "08:00")
                result["weekday_end"] = sched.get("close", "18:00")
                break
        else:
            result["weekday_start"] = "08:00"
            result["weekday_end"] = "18:00"

        # Saturday
        sat = bh.get("saturday")
        if isinstance(sat, dict):
            if sat.get("is_closed"):
                result["saturday_start"] = None
                result["saturday_end"] = None
            else:
                result["saturday_start"] = sat.get("open", "09:00")
                result["saturday_end"] = sat.get("close", "14:00")

        # Sunday
        sun = bh.get("sunday")
        if isinstance(sun, dict):
            result["sunday_closed"] = bool(sun.get("is_closed", True))
        else:
            result["sunday_closed"] = True

        # Holidays (pass through if present)
        if "holidays" in bh:
            result["holidays"] = bh["holidays"]

        return result

    @staticmethod
    def _to_shunya_qualification_rules(
        rules: Optional[list],
    ) -> Optional[list]:
        """
        Normalize qualification_rules for Shoonya.

        Otto allows combined 'action:value' (e.g. 'set_status:hot').
        Shoonya expects action and action_value as separate fields.
        Also ensures 'enabled' defaults to True and 'priority' defaults to 0.
        """
        if not rules or not isinstance(rules, list):
            return rules

        result = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule = dict(rule)

            action = rule.get("action", "")
            if isinstance(action, str) and ":" in action and "action_value" not in rule:
                parts = action.split(":", 1)
                rule["action"] = parts[0].strip()
                rule["action_value"] = parts[1].strip()

            rule.setdefault("enabled", True)
            rule.setdefault("priority", 0)
            result.append(rule)

        return result

    @classmethod
    def _to_shunya_service_prioritization(
        cls,
        service_prioritization: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Translate local service_prioritization shape to Shoonya's expected shape."""
        if not service_prioritization or not isinstance(service_prioritization, dict):
            return service_prioritization

        converted: Dict[str, Any] = dict(service_prioritization)
        raw_services = converted.get("services") or []
        shunya_services: list[dict[str, Any]] = []

        for item in raw_services:
            if not isinstance(item, dict):
                continue

            display_name = (
                (item.get("display_name") or item.get("service_name") or item.get("service_type") or "")
                .strip()
            )
            if not display_name:
                continue

            service_type = (item.get("service_type") or "").strip()
            if not service_type:
                # Derive stable service_type from display_name if missing.
                service_type = display_name.lower().replace(" ", "_")

            shunya_services.append(
                {
                    "service_type": service_type,
                    "display_name": display_name,
                    "priority": cls._normalize_shunya_priority(item.get("priority")),
                }
            )

        converted["services"] = shunya_services
        converted["default_priority"] = cls._normalize_shunya_priority(
            converted.get("default_priority")
        )
        return converted

    # Maps category_prefix -> default 'effect' value expected by Shoonya.
    _KEYWORD_EFFECT_MAP: dict[str, str] = {
        "urgency": "high_urgency",
        "budget": "budget_available",
        "objection": "objection_raised",
        "service": "service_mentioned",
    }

    @classmethod
    def _as_keyword_categories(cls, value: Any, category_prefix: str) -> list[dict[str, Any]]:
        """
        Normalize local keyword values to Shoonya KeywordCategory list.

        Shoonya's KeywordCategory requires: category, keywords, effect.
        Optional: phrases (list[str]), score_impact (float).

        Accepts:
        - list[str] (local simplified format) -> single category object
        - list[dict] (Shoonya/native format) -> ensure 'effect' present
        """
        if not value:
            return []

        default_effect = cls._KEYWORD_EFFECT_MAP.get(category_prefix, category_prefix)

        if isinstance(value, list):
            if all(isinstance(v, str) for v in value):
                keywords = [v.strip() for v in value if isinstance(v, str) and v.strip()]
                if not keywords:
                    return []
                return [
                    {
                        "category": f"{category_prefix}_default",
                        "keywords": keywords,
                        "effect": default_effect,
                    }
                ]

            # Already object format (or mixed). Keep dicts and ensure 'effect' field present.
            result = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                if "effect" not in item or not item["effect"]:
                    item = {**item, "effect": default_effect}
                result.append(item)
            return result

        return []

    @classmethod
    def _to_shunya_custom_keywords(
        cls,
        custom_keywords: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Translate local custom_keywords shape to Shoonya's expected shape."""
        if not custom_keywords or not isinstance(custom_keywords, dict):
            return custom_keywords

        converted: Dict[str, Any] = dict(custom_keywords)

        converted["urgency_keywords"] = cls._as_keyword_categories(
            converted.get("urgency_keywords"),
            "urgency",
        )
        converted["budget_keywords"] = cls._as_keyword_categories(
            converted.get("budget_keywords"),
            "budget",
        )
        converted["objection_keywords"] = cls._as_keyword_categories(
            converted.get("objection_keywords"),
            "objection",
        )

        service_keywords = converted.get("service_keywords")
        if isinstance(service_keywords, list):
            # Local simplified list[str] => map format expected by Shoonya.
            keywords = [v.strip() for v in service_keywords if isinstance(v, str) and v.strip()]
            converted["service_keywords"] = {"general": keywords} if keywords else {}
        elif not isinstance(service_keywords, dict):
            converted["service_keywords"] = {}

        return converted

    @staticmethod
    def _to_plain_object(value: Any) -> Any:
        """Convert Pydantic models to plain Python objects recursively."""
        if isinstance(value, BaseModel):
            return value.model_dump(exclude_none=True)
        if isinstance(value, list):
            return [TenantConfigService._to_plain_object(v) for v in value]
        if isinstance(value, dict):
            return {k: TenantConfigService._to_plain_object(v) for k, v in value.items()}
        return value

    async def _call_shunya_create(self, payload: dict) -> dict:
        """Call Shunya's POST /api/v1/tenant-config/ to create a config."""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/tenant-config/",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def _call_shunya_get(self, company_id: str) -> dict:
        """Call Shunya's GET /api/v1/tenant-config/{company_id}."""
        headers = {
            "X-API-Key": self.api_key,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/tenant-config/{company_id}",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def _call_shunya_update(self, company_id: str, payload: dict) -> dict:
        """Call Shunya's PUT /api/v1/tenant-config/{company_id} to update a config."""
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{self.base_url}/api/v1/tenant-config/{company_id}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_config(
        self,
        company_id: UUID,
        company_name: str,
        qualification_thresholds: Optional[Dict[str, Any]] = None,
        service_prioritization: Optional[Dict[str, Any]] = None,
        custom_keywords: Optional[Dict[str, Any]] = None,
        qualification_rules: Optional[list] = None,
        business_hours: Optional[Dict[str, Any]] = None,
        service_area: Optional[list] = None,
        industry: Optional[str] = "home_services",
        primary_services: Optional[list] = None,
    ) -> TenantConfigORM:
        """
        Create a tenant configuration.

        1. Calls Shunya API to create the config remotely.
        2. Stores the config + Shunya config_id in our DB.
        """
        # Check if config already exists locally
        existing = await self.get_config_by_company(company_id)
        if existing:
            raise ValueError(f"Configuration for company {company_id} already exists")

        # Normalize Pydantic model inputs from API routes to plain objects.
        qualification_thresholds = self._to_plain_object(qualification_thresholds)
        service_prioritization = self._to_plain_object(service_prioritization)
        custom_keywords = self._to_plain_object(custom_keywords)
        qualification_rules = self._to_plain_object(qualification_rules)
        business_hours = self._to_plain_object(business_hours)
        service_area = self._to_plain_object(service_area)
        primary_services = self._to_plain_object(primary_services)

        # Build payload for Shunya API
        shunya_payload: dict = {
            "company_id": str(company_id),
            "company_name": company_name,
        }
        if qualification_thresholds:
            shunya_payload["qualification_thresholds"] = self._to_shunya_qualification_thresholds(
                qualification_thresholds
            )
        if service_prioritization:
            shunya_payload["service_prioritization"] = self._to_shunya_service_prioritization(
                service_prioritization
            )
        if custom_keywords:
            shunya_payload["custom_keywords"] = self._to_shunya_custom_keywords(
                custom_keywords
            )
        if qualification_rules:
            shunya_payload["qualification_rules"] = self._to_shunya_qualification_rules(
                qualification_rules
            )
        if business_hours:
            shunya_payload["business_hours"] = self._to_shunya_business_hours(
                business_hours
            )
        if service_area:
            shunya_payload["service_area"] = service_area
        if industry:
            shunya_payload["industry"] = industry
        if primary_services:
            shunya_payload["primary_services"] = primary_services

        # Call Shunya API
        shunya_config_id = None
        shunya_version = 1
        try:
            shunya_response = await self._call_shunya_create(shunya_payload)
            shunya_config_id = shunya_response.get("config_id")
            shunya_version = shunya_response.get("version", 1)
            logger.info(f"Created tenant config on Shunya for company {company_id}: {shunya_config_id}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Shunya API error creating tenant config: {e.response.status_code} - {e.response.text}")
            raise ValueError(f"Shunya API error: {e.response.json().get('detail', e.response.text)}")
        except Exception as e:
            logger.error(f"Failed to call Shunya tenant-config API: {e}")
            traceback.print_exc()
            raise ValueError(f"Failed to create config on Shunya: {str(e)}")

        # Store locally in our DB
        orm_obj = TenantConfigORM(
            company_id=company_id,
            company_name=company_name,
            shunya_config_id=shunya_config_id,
            qualification_thresholds=qualification_thresholds,
            service_prioritization=service_prioritization,
            custom_keywords=custom_keywords,
            qualification_rules=qualification_rules,
            business_hours=business_hours,
            service_area=service_area,
            industry=industry,
            primary_services=primary_services,
            version=shunya_version,
            is_active=True,
        )
        self.session.add(orm_obj)
        await self.session.flush()
        await self.session.refresh(orm_obj)

        logger.info(f"Stored tenant config locally for company {company_id}")
        return orm_obj

    async def get_config_by_company(self, company_id: UUID) -> Optional[TenantConfigORM]:
        """Get tenant config from our local DB by company_id."""
        result = await self.session.execute(
            select(TenantConfigORM).where(
                TenantConfigORM.company_id == company_id,
                TenantConfigORM.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def get_config_with_shunya_fallback(self, company_id: UUID) -> Optional[TenantConfigORM]:
        """
        Get tenant config from local DB first.
        If not found locally, try fetching from Shunya and store it.
        """
        local = await self.get_config_by_company(company_id)
        if local:
            return local

        # Try fetching from Shunya
        try:
            shunya_data = await self._call_shunya_get(str(company_id))
            logger.info(f"Fetched tenant config from Shunya for company {company_id}")

            # Store locally
            orm_obj = TenantConfigORM(
                company_id=company_id,
                company_name=shunya_data.get("company_name", ""),
                shunya_config_id=shunya_data.get("config_id"),
                qualification_thresholds=shunya_data.get("qualification_thresholds"),
                service_prioritization=shunya_data.get("service_prioritization"),
                custom_keywords=shunya_data.get("custom_keywords"),
                qualification_rules=shunya_data.get("qualification_rules"),
                business_hours=shunya_data.get("business_hours"),
                service_area=shunya_data.get("service_area"),
                industry=shunya_data.get("industry"),
                primary_services=shunya_data.get("primary_services"),
                version=shunya_data.get("version", 1),
                is_active=shunya_data.get("is_active", True),
            )
            self.session.add(orm_obj)
            await self.session.flush()
            await self.session.refresh(orm_obj)
            return orm_obj
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            logger.error(f"Shunya API error fetching tenant config: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Failed to fetch tenant config from Shunya: {e}")
            return None

    async def update_config(
        self,
        company_id: UUID,
        updates: Dict[str, Any],
    ) -> Optional[TenantConfigORM]:
        """Update an existing tenant configuration on Shunya and locally."""
        orm_obj = await self.get_config_by_company(company_id)
        if not orm_obj:
            return None

        # Normalize incoming updates first (request may contain Pydantic models).
        updates = self._to_plain_object(updates)

        # Build Shoonya update payload using same mapping rules as create.
        shunya_updates: Dict[str, Any] = {}
        if "company_name" in updates and updates.get("company_name") is not None:
            shunya_updates["company_name"] = updates["company_name"]
        if "qualification_thresholds" in updates and updates.get("qualification_thresholds") is not None:
            shunya_updates["qualification_thresholds"] = self._to_shunya_qualification_thresholds(
                updates["qualification_thresholds"]
            )
        if "service_prioritization" in updates and updates.get("service_prioritization") is not None:
            shunya_updates["service_prioritization"] = self._to_shunya_service_prioritization(
                updates["service_prioritization"]
            )
        if "custom_keywords" in updates and updates.get("custom_keywords") is not None:
            shunya_updates["custom_keywords"] = self._to_shunya_custom_keywords(
                updates["custom_keywords"]
            )
        if "qualification_rules" in updates and updates.get("qualification_rules") is not None:
            shunya_updates["qualification_rules"] = self._to_shunya_qualification_rules(
                updates["qualification_rules"]
            )
        if "business_hours" in updates and updates.get("business_hours") is not None:
            shunya_updates["business_hours"] = self._to_shunya_business_hours(
                updates["business_hours"]
            )
        if "service_area" in updates and updates.get("service_area") is not None:
            shunya_updates["service_area"] = updates["service_area"]
        if "industry" in updates and updates.get("industry") is not None:
            shunya_updates["industry"] = updates["industry"]
        if "primary_services" in updates and updates.get("primary_services") is not None:
            shunya_updates["primary_services"] = updates["primary_services"]

        try:
            shunya_response = await self._call_shunya_update(str(company_id), shunya_updates)
            logger.info(
                f"Updated tenant config on Shunya for company {company_id}: "
                f"version={shunya_response.get('version')}"
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Shunya API error updating tenant config: "
                f"{e.response.status_code} - {e.response.text}"
            )
            raise ValueError(f"Shunya API error: {e.response.json().get('detail', e.response.text)}")
        except Exception as e:
            logger.error(f"Failed to call Shunya tenant-config update API: {e}")
            traceback.print_exc()
            raise ValueError(f"Failed to update config on Shunya: {str(e)}")

        # Persist local DB after remote update succeeds.
        for key, value in updates.items():
            if hasattr(orm_obj, key) and key not in ("id", "company_id", "created_at"):
                setattr(orm_obj, key, value)

        orm_obj.version = shunya_response.get("version", (orm_obj.version or 0) + 1)
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return orm_obj
