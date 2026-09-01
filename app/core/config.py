"""
Application configuration.

Uses Pydantic Settings for type-safe environment variable management.
Loads environment variables from .env file using python-dotenv.
"""
import os
from typing import List
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Load environment variables from .env file
load_dotenv(override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    APP_ENV: str = Field(
        default=os.getenv("APP_ENV", "DEV"),
        description="Application environment: DEV (bypasses auth) or PROD (requires auth)"
    )

    # Database (optional for development - can use SQLite)
    DATABASE_URL: str = Field(
        default=os.getenv("DATABASE_URL"),
        description="Database connection string (PostgreSQL with asyncpg or SQLite with aiosqlite)"
    )
    DB_SSL_MODE: str = Field(
        default=os.getenv("DB_SSL_MODE", ""),
        description=(
            "PostgreSQL TLS mode handed to asyncpg: disable, allow, prefer, require, "
            "verify-ca or verify-full. Empty means take it from DATABASE_URL, else "
            "require for remote hosts and prefer for localhost."
        )
    )
    DB_SECRET_ARN: str = Field(
        default=os.getenv("DB_SECRET_ARN", ""),
        description="AWS Secrets Manager ARN holding the rotating database password. "
                    "When set, the password embedded in DATABASE_URL is used only as a fallback."
    )

    # Redis
    REDIS_URL: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    # Shoonya/UWC Integration (optional - can be empty for development)
    UWC_BASE_URL: str = Field(
        default=os.getenv("UWC_BASE_URL", "https://ottoai.shunyalabs.ai"),
        description="Shoonya/UWC API base URL"
    )
    UWC_API_KEY: str = Field(default=os.getenv("UWC_API_KEY", ""), description="UWC API key (legacy)")
    API_KEY: str = Field(default=os.getenv("API_KEY", ""), description="Shunya API key for X-API-Key header")
    UWC_HMAC_SECRET: str = Field(default=os.getenv("UWC_HMAC_SECRET", ""), description="HMAC secret for webhook verification")
    UWC_JWT_SECRET: str = Field(default=os.getenv("UWC_JWT_SECRET", ""), description="JWT secret for UWC")
    UWC_VERSION: str = Field(default=os.getenv("UWC_VERSION", "v1"), description="UWC API version")

    # OpenAI (fallback LLM)
    OPENAI_API_KEY: str = Field(default=os.getenv("OPENAI_API_KEY", ""), description="OpenAI API key")
    INTENT_CLASSIFICATION_MODEL: str = Field(
        default=os.getenv("INTENT_CLASSIFICATION_MODEL", "gpt-4o-mini"),
        description="OpenAI model for inbound SMS intent classification",
    )

    # Twilio (webhook signature validation for inbound SMS)
    TWILIO_AUTH_TOKEN: str = Field(
        default=os.getenv("TWILIO_AUTH_TOKEN", ""),
        description="Twilio auth token; used to validate inbound SMS webhooks when set",
    )

    # Vector DB Configuration
    VECTOR_DB_PROVIDER: str = Field(
        default=os.getenv("VECTOR_DB_PROVIDER", "pinecone"),
        description="Vector DB provider: pinecone, weaviate, or pgvector"
    )



    PINECONE_API_KEY: str = Field(default=os.getenv("PINECONE_API_KEY", ""), description="Pinecone API key")
    PINECONE_ENVIRONMENT: str = Field(default=os.getenv("PINECONE_ENVIRONMENT", ""), description="Pinecone environment")
    PINECONE_INDEX_NAME: str = Field(default=os.getenv("PINECONE_INDEX_NAME", "otto-embeddings"), description="Pinecone index name")
    WEAVIATE_URL: str = Field(default=os.getenv("WEAVIATE_URL", ""), description="Weaviate URL")

    # AWS S3
    AWS_ACCESS_KEY_ID: str = Field(default=os.getenv("AWS_ACCESS_KEY_ID", ""), description="AWS access key")
    AWS_SECRET_ACCESS_KEY: str = Field(default=os.getenv("AWS_SECRET_ACCESS_KEY", ""), description="AWS secret key")
    AWS_REGION: str = Field(default=os.getenv("AWS_REGION", "us-east-1"), description="AWS region")
    S3_BUCKET: str = Field(default=os.getenv("S3_BUCKET", ""), description="S3 bucket name (deprecated: use S3_DOCUMENTS_BUCKET and S3_AUDIO_BUCKET)")
    S3_DOCUMENTS_BUCKET: str = Field(default=os.getenv("S3_DOCUMENTS_BUCKET", ""), description="S3 bucket name for documents")
    S3_AUDIO_BUCKET: str = Field(default=os.getenv("S3_AUDIO_BUCKET", ""), description="S3 bucket name for audio files")

    # API Configuration
    API_URL: str = Field(default=os.getenv("API_URL", "http://localhost:8000"), description="Public API URL")
    APP_URL: str = Field(default=os.getenv("APP_URL", "http://localhost:3000"), description="Public app URL")
    ALLOWED_ORIGINS: str = Field(
        default=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000"),
        description="Allowed CORS origins (comma-separated)"
    )
    ALLOWED_HOSTS: str = Field(
        default=os.getenv("ALLOWED_HOSTS", "*"),
        description="Allowed hosts (comma-separated)"
    )

    # Logging
    LOG_LEVEL: str = Field(default=os.getenv("LOG_LEVEL", "INFO"), description="Logging level")

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default=os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production"),
        description="Secret key for JWT token signing (MUST be changed in production)"
    )
    JWT_ALGORITHM: str = Field(
        default=os.getenv("JWT_ALGORITHM", "HS256"),
        description="JWT signing algorithm"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
        description="Access token expiration time in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        description="Refresh token expiration time in days"
    )

    # Encryption Key
    ENCRYPTION_KEY: str = Field(default=os.getenv("ENCRYPTION_KEY", ""), description="Encryption key")

    # Mailgun Configuration
    MAILGUN_API_KEY: str = Field(default=os.getenv("MAILGUN_API_KEY", ""), description="Mailgun API key")
    MAILGUN_DOMAIN: str = Field(default=os.getenv("MAILGUN_DOMAIN", ""), description="Mailgun domain")
    MAILGUN_BASE_URL: str = Field(
        default=os.getenv("MAILGUN_BASE_URL", "https://api.mailgun.net/v3"),
        description="Mailgun API base URL"
    )
    MAILGUN_FROM_EMAIL: str = Field(
        default=os.getenv("MAILGUN_FROM_EMAIL", "noreply@example.com"),
        description="Default sender email address"
    )

    # Google Maps
    GOOGLE_MAPS_API_KEY: str = Field(default=os.getenv("GOOGLE_MAPS_API_KEY", ""), description="Google Maps API key for geocoding")

    # GoHighLevel Configuration
    GHL_PUBLIC_KEY: str = Field(default=os.getenv("GHL_PUBLIC_KEY", ""), description="GoHighLevel public key")

    # ServiceTitan
    ST_APP_KEY: str = Field(
        default=os.getenv("ST_APP_KEY", ""),
        description="ServiceTitan platform app key (shared across all tenants)",
    )
    ST_ENV: str = Field(
        default=os.getenv("ST_ENV", "production"),
        description="ServiceTitan environment: production or integration (shared across all tenants)",
    )
    ST_WORKER_SECRET: str = Field(
        default=os.getenv("ST_WORKER_SECRET", ""),
        description="Shared secret for ST worker → webhook auth",
    )

    # Retell AI voice agent
    VOICE_AGENT_SECRET: str = Field(
        default=os.getenv("VOICE_AGENT_SECRET", ""),
        description="Shared secret for Retell custom tools → /api/v1/voice-agent/*",
    )
    VOICE_AGENT_DEFAULT_COMPANY_ID: str = Field(
        default=os.getenv("VOICE_AGENT_DEFAULT_COMPANY_ID", ""),
        description="Default Otto company UUID provisioned on the Retell agent",
    )
    RETELL_API_KEY: str = Field(
        default=os.getenv("RETELL_API_KEY", ""),
        description="Retell API key for webhook signature verification",
    )
    RETELL_AGENT_COMPANY_MAP: str = Field(
        default=os.getenv("RETELL_AGENT_COMPANY_MAP", "{}"),
        description='JSON map of retell agent_id → company UUID, e.g. {"agent_abc":"uuid"}',
    )

    # Twilio (Masked Communications)
    TWILIO_ACCOUNT_SID: str = Field(default=os.getenv("TWILIO_ACCOUNT_SID", ""), description="Twilio Account SID")
    TWILIO_AUTH_TOKEN: str = Field(default=os.getenv("TWILIO_AUTH_TOKEN", ""), description="Twilio Auth Token")
    TWILIO_SYSTEM_NUMBER: str = Field(default=os.getenv("TWILIO_SYSTEM_NUMBER", ""), description="Twilio system number for OTP")

    # Feature Flags
    ENABLE_CELERY: bool = Field(default=os.getenv("ENABLE_CELERY", "False").lower() == "true", description="Enable Celery for background jobs")
    ENABLE_VECTOR_DB: bool = Field(default=os.getenv("ENABLE_VECTOR_DB", "True").lower() == "true", description="Enable vector DB for RAG")
    ENABLE_DOCS: bool = Field(
        default=os.getenv("ENABLE_DOCS", "True").lower() == "true",
        description="Enable Swagger/ReDoc documentation (set to False in production)"
    )
    AUTO_CREATE_TABLES: bool = Field(
        default=os.getenv("AUTO_CREATE_TABLES", "False").lower() == "true",
        description="Auto-create database tables on startup (development only, disabled in production). Use Alembic migrations for production."
    )

    # Appointment Reminders
    APPOINTMENT_REMINDER_TZ: str = Field(
        default=os.getenv("APPOINTMENT_REMINDER_TZ", "America/New_York"),
        description="IANA timezone used to compute day-before / morning-of reminder times",
    )
    APPOINTMENT_MORNING_REMINDER_HOUR: int = Field(
        default=int(os.getenv("APPOINTMENT_MORNING_REMINDER_HOUR", "8")),
        description="Local hour (0-23) at which the morning-of appointment reminder fires",
    )
    APPOINTMENT_DAY_BEFORE_REMINDER_HOUR: int = Field(
        default=int(os.getenv("APPOINTMENT_DAY_BEFORE_REMINDER_HOUR", "9")),
        description="Local hour (0-23) at which the day-before appointment reminder fires",
    )
    APPOINTMENT_REMINDER_GRACE_MINUTES: int = Field(
        default=int(os.getenv("APPOINTMENT_REMINDER_GRACE_MINUTES", "15")),
        description="Minutes after a reminder due_at during which the reminder is still eligible to fire",
    )

    # Rehash (missed-revenue opportunity scanner)
    REHASH_QUALIFIED_UNBOOKED_DAYS: int = Field(
        default=int(os.getenv("REHASH_QUALIFIED_UNBOOKED_DAYS", "7")),
        description="Days since last update before a qualified-but-unbooked lead becomes a rehash candidate",
    )
    REHASH_APPOINTMENT_PENDING_DAYS: int = Field(
        default=int(os.getenv("REHASH_APPOINTMENT_PENDING_DAYS", "3")),
        description="Days since a ran appointment with open outcome before it becomes a rehash candidate",
    )
    REHASH_STALE_LEAD_DAYS: int = Field(
        default=int(os.getenv("REHASH_STALE_LEAD_DAYS", "14")),
        description="Days of no activity before an open-pipeline lead becomes a stale-lead rehash candidate",
    )
    REHASH_NOTIFICATION_GRACE_MINUTES: int = Field(
        default=int(os.getenv("REHASH_NOTIFICATION_GRACE_MINUTES", "60")),
        description="Minutes after a rehash due_at during which the rehash notification is still eligible to fire",
    )

    # Contextual follow-up agent (proactive draft generation)
    CONTEXTUAL_FOLLOWUP_ENABLED: bool = Field(
        default=os.getenv("CONTEXTUAL_FOLLOWUP_ENABLED", "True").lower() == "true",
        description="Enable the daily scheduled run of the contextual follow-up agent (propose-only drafts)",
    )

    # Recording reconciliation (recovery for stuck analysis jobs)
    RECORDING_STUCK_THRESHOLD_MINUTES: int = Field(
        default=int(os.getenv("RECORDING_STUCK_THRESHOLD_MINUTES", "30")),
        description="Minutes an appointment may sit in analysis_status='processing' before reconciliation polls Shunya",
    )
    RECORDING_MAX_PROCESSING_HOURS: int = Field(
        default=int(os.getenv("RECORDING_MAX_PROCESSING_HOURS", "6")),
        description="Hard ceiling: a recording stuck in 'processing' longer than this is marked failed (timed out)",
    )
    RECORDING_RECONCILE_BATCH_LIMIT: int = Field(
        default=int(os.getenv("RECORDING_RECONCILE_BATCH_LIMIT", "100")),
        description="Max stuck recordings reconciled per scheduler run",
    )
    RECORDING_RECONCILE_INTERVAL_MINUTES: int = Field(
        default=int(os.getenv("RECORDING_RECONCILE_INTERVAL_MINUTES", "30")),
        description="How often the stuck-recording reconciliation job runs (minutes)",
    )

    # Generic task reminders (call_back / follow_up / post-meeting)
    GENERIC_TASK_REMINDER_GRACE_MINUTES: int = Field(
        default=int(os.getenv("GENERIC_TASK_REMINDER_GRACE_MINUTES", "30")),
        description="Minutes after a generic task's due_at during which its (single) reminder is still eligible to fire; makes firing restart/downtime-safe",
    )

    @property
    def allowed_origins_list(self) -> List[str]:
        """Get allowed origins as a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def allowed_hosts_list(self) -> List[str]:
        """Get allowed hosts as a list."""
        return [host.strip() for host in self.ALLOWED_HOSTS.split(",") if host.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.ENVIRONMENT == "development"

    @property
    def is_dev_mode(self) -> bool:
        """Check if running in DEV mode (auth bypass enabled)."""
        return self.APP_ENV.upper() == "DEV"

    @property
    def is_prod_mode(self) -> bool:
        """Check if running in PROD mode (auth required)."""
        return self.APP_ENV.upper() == "PROD"


# Global settings instance
settings = Settings()

