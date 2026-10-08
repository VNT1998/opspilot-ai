from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Project metadata
    PROJECT_NAME: str = "OpsPilot AI"
    PROJECT_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = True

    # Security & Auth
    SECRET_KEY: str = "insecure-dev-secret-key-change-in-production-opspilot-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Demo Seed Credentials (LOCAL DEVELOPMENT ONLY)
    DEMO_ADMIN_PASSWORD: str = "admin123"
    DEMO_OPS_PASSWORD: str = "ops123"
    DEMO_REVIEWER_PASSWORD: str = "reviewer123"
    DEMO_VIEWER_PASSWORD: str = "viewer123"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./opspilot.db"
    DB_ECHO: bool = False

    # Redis & Asynchronous Worker
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_IN_MEMORY_QUEUE: bool = True  # True allows self-contained execution without Redis server

    # Storage
    STORAGE_TYPE: Literal["local", "s3"] = "local"
    LOCAL_STORAGE_PATH: str = "./data/storage"
    S3_BUCKET_NAME: str = "opspilot-documents"
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: Optional[str] = None
    MAX_UPLOAD_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt"]

    # AI & LLM Provider Configuration
    DEFAULT_LLM_PROVIDER: Literal["mock", "openai", "anthropic"] = "mock"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Business Validation & Automation Rules
    AUTO_APPROVE_CONFIDENCE_THRESHOLD: float = 0.85
    VARIANCE_TOLERANCE_PERCENT: float = 2.0  # 2% variance allowed
    VARIANCE_TOLERANCE_ABSOLUTE: float = 5.0  # $5.00 tolerance
    HIGH_VALUE_THRESHOLD: float = 10000.0  # Invoices >= $10k strictly require human review

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if (
                not self.SECRET_KEY
                or self.SECRET_KEY == "insecure-dev-secret-key-change-in-production-opspilot-2026"
                or len(self.SECRET_KEY) < 32
            ):
                raise ValueError(
                    "Production environment requires a strong, explicit SECRET_KEY with at least 32 characters."
                )
        return self


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Ensure local storage path exists
    if settings.STORAGE_TYPE == "local":
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    return settings
