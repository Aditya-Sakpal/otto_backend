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

        # Build payload for Shunya API
        shunya_payload: dict = {
            "company_id": str(company_id),
            "company_name": company_name,
        }
        if qualification_thresholds:
            shunya_payload["qualification_thresholds"] = qualification_thresholds
        if service_prioritization:
            shunya_payload["service_prioritization"] = service_prioritization
        if custom_keywords:
            shunya_payload["custom_keywords"] = custom_keywords
        if qualification_rules:
            shunya_payload["qualification_rules"] = qualification_rules
        if business_hours:
            shunya_payload["business_hours"] = business_hours
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
        """Update an existing tenant configuration locally."""
        orm_obj = await self.get_config_by_company(company_id)
        if not orm_obj:
            return None

        for key, value in updates.items():
            if hasattr(orm_obj, key) and key not in ("id", "company_id", "created_at"):
                setattr(orm_obj, key, value)

        orm_obj.version = (orm_obj.version or 0) + 1
        await self.session.flush()
        await self.session.refresh(orm_obj)
        return orm_obj
