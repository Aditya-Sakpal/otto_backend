"""
Per-company configuration.

Stores Twilio from-number and timezone per company.
Loaded from COMPANY_CONFIGS env var (JSON string).
"""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

from contextual_follow_up_agent.config.logging import get_logger
from contextual_follow_up_agent.config.settings import settings

logger = get_logger(__name__)


class CompanyConfig(BaseModel):
    """Per-company configuration."""

    company_id: str
    twilio_from_number: str  # E.164: "+15125550123"
    timezone: str = "America/Chicago"


class CompanyConfigStore:
    """In-memory company config store loaded from env var."""

    def __init__(self) -> None:
        self._configs: dict[str, CompanyConfig] = {}
        self._load()

    def _load(self) -> None:
        """Load configs from COMPANY_CONFIGS env var (JSON)."""
        try:
            raw = json.loads(settings.COMPANY_CONFIGS)
            for company_id, cfg in raw.items():
                cfg["company_id"] = company_id
                self._configs[company_id] = CompanyConfig(**cfg)
            logger.info("Company configs loaded", count=len(self._configs))
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to load company configs", error=str(e))

    def get(self, company_id: str) -> Optional[CompanyConfig]:
        """Get config for a company."""
        return self._configs.get(company_id)

    def list_all(self) -> list[CompanyConfig]:
        """List all company configs."""
        return list(self._configs.values())
