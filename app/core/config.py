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
load_dotenv()


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
        default=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./otto.db"),
        description="Database connection string (PostgreSQL with asyncpg or SQLite with aiosqlite)"
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
    S3_BUCKET: str = Field(default=os.getenv("S3_BUCKET", ""), description="S3 bucket name")

    # API Configuration
    API_URL: str = Field(default=os.getenv("API_URL", "http://localhost:8000"), description="Public API URL")
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
        default=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")),
        description="Access token expiration time in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        description="Refresh token expiration time in days"
    )

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

