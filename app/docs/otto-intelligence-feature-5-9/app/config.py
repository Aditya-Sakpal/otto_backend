"""
Configuration management for Otto Intelligence Service
"""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    API_KEY: str = Field(..., env="API_KEY")
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    
    # MongoDB
    MONGODB_URL: str = Field(..., env="MONGODB_URL")
    MONGODB_DB_NAME: str = Field(default="otto-ai-storage", env="MONGODB_DB_NAME")
    
    # Redis
    REDIS_URL: str = Field(..., env="REDIS_URL")
    
    # Milvus Zilliz Cloud
    MILVUS_URI: str = Field(..., env="MILVUS_URI")
    MILVUS_TOKEN: str = Field(..., env="MILVUS_TOKEN")
    MILVUS_COLLECTION: str = Field(default="otto_intelligence_v1", env="MILVUS_COLLECTION")
    
    # LLM APIs
    LLM_PROVIDER: str = Field(default="groq", env="LLM_PROVIDER")  # Options: "groq", "anthropic", "openai"
    
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-4-turbo-preview", env="OPENAI_MODEL")
    
    GROQ_API_KEY: Optional[str] = Field(default=None, env="GROQ_API_KEY")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile", env="GROQ_MODEL")
    GROQ_API_BASE: str = Field(default="https://api.groq.com/openai/v1", env="GROQ_API_BASE")
    
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL: str = Field(default="claude-3-5-sonnet-20240620", env="ANTHROPIC_MODEL")
    
    # Embedding Model (HuggingFace)
    EMBEDDING_MODEL: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    EMBEDDING_DIMENSION: int = Field(default=384, env="EMBEDDING_DIMENSION")
    
    # Transcription
    SHUNYA_API_URL: Optional[str] = Field(default=None, env="SHUNYA_API_URL")
    SHUNYA_API_KEY: Optional[str] = Field(default=None, env="SHUNYA_API_KEY")
    ASSEMBLYAI_API_KEY: Optional[str] = Field(default=None, env="ASSEMBLYAI_API_KEY")
    
    # Diarization Settings
    ENABLE_DIARIZATION: bool = Field(default=True, env="ENABLE_DIARIZATION")
    ENABLE_LLM_DIARIZATION_FALLBACK: bool = Field(default=True, env="ENABLE_LLM_DIARIZATION_FALLBACK")
    ENABLE_LLM_SPEAKER_LABELING: bool = Field(default=True, env="ENABLE_LLM_SPEAKER_LABELING")
    ENABLE_HYBRID_DIARIZATION_VERIFICATION: bool = Field(default=True, env="ENABLE_HYBRID_DIARIZATION_VERIFICATION")  # Verify API diarization with LLM
    DIARIZATION_PRIORITY: str = Field(default="llm", env="DIARIZATION_PRIORITY")  # "api" or "llm"
    DIARIZATION_LLM_MODEL: str = Field(default="llama-3.3-70b-versatile", env="DIARIZATION_LLM_MODEL")  # Better model for diarization - another option openai/gpt-oss-20b - llama-3.3-70b-versatile
    
    # AWS S3
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    S3_BUCKET: Optional[str] = Field(default=None, env="S3_BUCKET")
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    
    # Celery
    CELERY_BROKER_URL: Optional[str] = Field(default=None, env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: Optional[str] = Field(default=None, env="CELERY_RESULT_BACKEND")
    
    # Logging
    LOG_LEVEL: str = Field(default="DEBUG", env="LOG_LEVEL")
    
    # SOP Settings
    SOP_REANALYSIS_DEFAULT_LOOKBACK_DAYS: int = Field(
        default=14, 
        env="SOP_REANALYSIS_DEFAULT_LOOKBACK_DAYS",
        description="Default number of days to look back when re-analyzing calls with new SOP versions"
    )
    SOP_METRICS_CHUNK_SIZE: int = Field(
        default=10,
        env="SOP_METRICS_CHUNK_SIZE",
        description="Number of SOP metrics to evaluate per LLM call (chunking for cost efficiency)"
    )
    SOP_EVAL_MAX_TOKENS_PER_CHUNK: int = Field(
        default=4000,
        env="SOP_EVAL_MAX_TOKENS_PER_CHUNK",
        description="Max completion tokens per chunk evaluation (lower = cheaper, needs enough for output)"
    )
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in ["development", "dev", "local"]
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ["production", "prod"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get settings singleton"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Create settings instance for direct import
settings = get_settings()

