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
    DEMO_ADMIN_PASSWORD: str = "AdminDemo2026!"
    DEMO_OPS_PASSWORD: str = "OpsDemo2026!"
    DEMO_REVIEWER_PASSWORD: str = "ReviewerDemo2026!"
    DEMO_VIEWER_PASSWORD: str = "ViewerDemo2026!"

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
    S3_ADDRESSING_STYLE: Literal["auto", "path", "virtual"] = "auto"
    MAX_UPLOAD_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt"]

    # AI & LLM Provider Configuration
    DEFAULT_LLM_PROVIDER: Literal["mock", "openai"] = "mock"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_BASE_URL: Optional[str] = None  # Configurable for Ollama / vLLM (e.g. https://ollama.calmalpha.in/v1)
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Business Validation & Automation Rules
    AUTO_APPROVE_CONFIDENCE_THRESHOLD: float = 0.85
    VARIANCE_TOLERANCE_PERCENT: float = 2.0  # 2% variance allowed
    VARIANCE_TOLERANCE_ABSOLUTE: float = 5.0  # $5.00 tolerance
    HIGH_VALUE_THRESHOLD: float = 10000.0  # Invoices >= $10k strictly require human review
    RAG_MIN_RELEVANCE_SCORE: float = 0.01

    # CORS & Network Security
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    TRUSTED_PROXIES: List[str] = []

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

            # 2. DEBUG must be disabled in production
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production.")

            # 3. Database URL must be PostgreSQL in production
            if not (
                self.DATABASE_URL.startswith("postgresql://") or self.DATABASE_URL.startswith("postgresql+asyncpg://")
            ):
                raise ValueError(
                    "Production database requires PostgreSQL (postgresql+asyncpg://...). SQLite is prohibited in production."
                )

            # 4. No Mock LLM in production
            if self.DEFAULT_LLM_PROVIDER == "mock":
                raise ValueError("DEFAULT_LLM_PROVIDER cannot be 'mock' in production.")

            # 5. Provider credentials check
            if self.DEFAULT_LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required in production when DEFAULT_LLM_PROVIDER=openai.")

            # 6. No demo seed in production
            if self.ENABLE_DEMO_SEED:
                raise ValueError("ENABLE_DEMO_SEED must be False in production.")

            # 7. Durable Redis queue required in production
            if self.WORKER_MODE != "redis" or self.USE_IN_MEMORY_QUEUE:
                raise ValueError(
                    "Production environment strictly requires WORKER_MODE='redis' and USE_IN_MEMORY_QUEUE=False; in-memory queue is prohibited in production."
                )

            # 8. Object storage required in production
            if self.STORAGE_TYPE != "s3":
                raise ValueError("STORAGE_TYPE must be 's3' in production.")

            # 9. CORS origins cannot contain localhost in production
            if not self.CORS_ORIGINS or any(
                "localhost" in origin.lower() or "127.0.0.1" in origin for origin in self.CORS_ORIGINS
            ):
                raise ValueError(
                    "Production CORS_ORIGINS must be explicitly configured and cannot contain localhost or 127.0.0.1."
                )

        # Non-production check: if demo seeding is enabled, demo passwords cannot be empty
        if self.ENABLE_DEMO_SEED:
            if not all(
                [
                    self.DEMO_ADMIN_PASSWORD,
                    self.DEMO_OPS_PASSWORD,
                    self.DEMO_REVIEWER_PASSWORD,
                    self.DEMO_VIEWER_PASSWORD,
                ]
            ):
                raise ValueError("When ENABLE_DEMO_SEED is True, all demo passwords must be non-empty.")

        return self


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    # Ensure local storage path exists
    if settings.STORAGE_TYPE == "local":
        Path(settings.LOCAL_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    return settings
