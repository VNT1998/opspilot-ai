import pytest
from pydantic import ValidationError
from app.core.config import Settings


BASE_PROD_KWARGS = {
    "ENVIRONMENT": "production",
    "DEBUG": False,
    "SECRET_KEY": "a-very-long-production-grade-secret-key-32chars!",
    "DATABASE_URL": "postgresql+asyncpg://opspilot:securepass@localhost:5432/opspilot",
    "DEFAULT_LLM_PROVIDER": "openai",
    "OPENAI_API_KEY": "sk-valid-production-key",
    "ENABLE_DEMO_SEED": False,
    "USE_IN_MEMORY_QUEUE": False,
    "WORKER_MODE": "redis",
    "STORAGE_TYPE": "s3",
    "CORS_ORIGINS": ["https://app.opspilot.ai"],
}


def test_production_valid_instantiates_cleanly():
    settings = Settings(**BASE_PROD_KWARGS)
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
    assert settings.WORKER_MODE == "redis"
    assert settings.USE_IN_MEMORY_QUEUE is False
    assert settings.STORAGE_TYPE == "s3"


def test_production_rejects_debug_mode():
    kwargs = {**BASE_PROD_KWARGS, "DEBUG": True}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "DEBUG must be False in production" in str(exc.value)


def test_production_rejects_sqlite_database():
    kwargs = {**BASE_PROD_KWARGS, "DATABASE_URL": "sqlite+aiosqlite:///./opspilot.db"}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "Production database requires PostgreSQL" in str(exc.value)


def test_production_rejects_mock_llm():
    kwargs = {**BASE_PROD_KWARGS, "DEFAULT_LLM_PROVIDER": "mock"}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "DEFAULT_LLM_PROVIDER cannot be 'mock' in production" in str(exc.value)


def test_production_requires_provider_api_key():
    kwargs = {**BASE_PROD_KWARGS, "DEFAULT_LLM_PROVIDER": "openai", "OPENAI_API_KEY": None}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "OPENAI_API_KEY is required in production" in str(exc.value)


def test_production_rejects_demo_seed():
    kwargs = {**BASE_PROD_KWARGS, "ENABLE_DEMO_SEED": True}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "ENABLE_DEMO_SEED must be False in production" in str(exc.value)


def test_production_rejects_in_memory_queue():
    kwargs = {**BASE_PROD_KWARGS, "USE_IN_MEMORY_QUEUE": True}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "in-memory queue is prohibited in production" in str(exc.value)


def test_production_rejects_worker_mode_in_process():
    # OPS-002: Verify that setting USE_IN_MEMORY_QUEUE=False but WORKER_MODE="in_process" fails
    kwargs = {**BASE_PROD_KWARGS, "USE_IN_MEMORY_QUEUE": False, "WORKER_MODE": "in_process"}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "WORKER_MODE='redis'" in str(exc.value)


def test_production_rejects_local_storage():
    kwargs = {**BASE_PROD_KWARGS, "STORAGE_TYPE": "local"}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "STORAGE_TYPE must be 's3' in production" in str(exc.value)


def test_production_rejects_localhost_cors():
    kwargs = {**BASE_PROD_KWARGS, "CORS_ORIGINS": ["http://localhost:5173"]}
    with pytest.raises(ValidationError) as exc:
        Settings(**kwargs)
    assert "Production CORS_ORIGINS must be explicitly configured" in str(exc.value)


def test_production_rejects_placeholder_secrets():
    for bad_secret in [
        "change-me-locally-with-a-very-long-key-string",
        "generate-a-long-random-secret-key-at-least-32-chars",
        "insecure-dev-secret-key-change-in-production-opspilot-2026",
    ]:
        kwargs = {**BASE_PROD_KWARGS, "SECRET_KEY": bad_secret}
        with pytest.raises(ValidationError) as exc:
            Settings(**kwargs)
        assert "cannot contain default placeholders" in str(exc.value)


def test_development_rejects_empty_demo_passwords_when_seed_enabled():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="development",
            ENABLE_DEMO_SEED=True,
            DEMO_ADMIN_PASSWORD="",
        )
    assert "When ENABLE_DEMO_SEED is True, all demo passwords must be non-empty" in str(exc.value)
