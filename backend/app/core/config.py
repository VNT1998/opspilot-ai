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

    # Demo Seed Credentials & Flag (DEVELOPMENT ONLY)
    ENABLE_DEMO_SEED: bool = True
    DEMO_ADMIN_PASSWORD: str = ""
    DEMO_OPS_PASSWORD: str = ""
    DEMO_REVIEWER_PASSWORD: str = ""
    DEMO_VIEWER_PASSWORD: str = ""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./opspilot.db"
    DB_ECHO: bool = False

    # Redis & Asynchronous Worker
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_IN_MEMORY_QUEUE: bool = True  # True allows self-contained execution without Redis server
    WORKER_MODE: Literal["in_process", "redis"] = "in_process"

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
    RAG_MIN_RELEVANCE_SCORE: float = 0.01

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
            # 1. Secret Key validation
            known_insecure = (
                "insecure",
                "dev-secret",
                "change-me",
                "generate-a-long",
                "admin123",
                "opspilot-2026",
            )
            if (
                not self.SECRET_KEY
                or len(self.SECRET_KEY) < 32
                or any(k in self.SECRET_KEY.lower() for k in known_insecure)
            ):
                raise ValueError(
                    "Production environment requires a strong, explicit SECRET_KEY with at least 32 characters, and cannot contain default placeholders."
                )

            # 2. No Mock LLM in production
            if self.DEFAULT_LLM_PROVIDER == "mock":
                raise ValueError("DEFAULT_LLM_PROVIDER cannot be 'mock' in production.")

            # 3. Provider credentials check
            if self.DEFAULT_LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required in production when DEFAULT_LLM_PROVIDER=openai.")
            if self.DEFAULT_LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY is required in production when DEFAULT_LLM_PROVIDER=anthropic.")

            # 4. No demo seed in production
            if self.ENABLE_DEMO_SEED:
                raise ValueError("ENABLE_DEMO_SEED must be False in production.")

            # 5. Durable queue required in production
            if self.USE_IN_MEMORY_QUEUE:
                raise ValueError(
                    "USE_IN_MEMORY_QUEUE cannot be True in production; a durable queue backend is required."
                )

            # 6. Object storage required in production
            if self.STORAGE_TYPE != "s3":
                raise ValueError("STORAGE_TYPE must be 's3' in production.")

        return self


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Ensure local storage path exists
    if settings.STORAGE_TYPE == "local":
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    return settings
