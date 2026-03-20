"""
Global application settings.

Uses Pydantic Settings v2 for type-safe environment variable management.
Follows the same pattern as speed-to-lead/config/settings.py.
"""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Resolve project-root .env (OTTO/.env) regardless of CWD
    _env_path = Path(__file__).resolve().parents[5] / ".env"

    model_config = SettingsConfigDict(
        env_file=str(_env_path),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Otto-Backend PostgreSQL
    DATABASE_URL: str = ""

    # Local SQLite
    LOCAL_DB_PATH: str = "data/follow_up.db"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""

    # Per-company config (JSON string)
    COMPANY_CONFIGS: str = "{}"

    # Agent behavior
    DRY_RUN: bool = True
    AUTO_EXECUTE: bool = False

    # Intelligence gates
    MASKED_COMMS_ENABLED: bool = False

    # Cadence defaults (days)
    CADENCE_ATTEMPT_1_DAYS: int = 3
    CADENCE_ATTEMPT_2_DAYS: int = 7
    CADENCE_ATTEMPT_3_DAYS: int = 14
    MAX_ATTEMPTS: int = 3
    TIMING_OVERRIDE_MIN_CONFIDENCE: float = 0.7

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
