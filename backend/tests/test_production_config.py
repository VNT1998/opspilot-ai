import pytest
from pydantic import ValidationError
from app.core.config import Settings


def test_production_rejects_mock_llm():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-production-grade-secret-key-32chars!",
            DEFAULT_LLM_PROVIDER="mock",
            ENABLE_DEMO_SEED=False,
            USE_IN_MEMORY_QUEUE=False,
            STORAGE_TYPE="s3",
        )
    assert "DEFAULT_LLM_PROVIDER cannot be 'mock' in production" in str(exc.value)


def test_production_requires_provider_api_key():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-production-grade-secret-key-32chars!",
            DEFAULT_LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            ENABLE_DEMO_SEED=False,
            USE_IN_MEMORY_QUEUE=False,
            STORAGE_TYPE="s3",
        )
    assert "OPENAI_API_KEY is required in production" in str(exc.value)


def test_production_rejects_demo_seed():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-production-grade-secret-key-32chars!",
            DEFAULT_LLM_PROVIDER="openai",
            OPENAI_API_KEY="sk-valid-production-key",
            ENABLE_DEMO_SEED=True,
            USE_IN_MEMORY_QUEUE=False,
            STORAGE_TYPE="s3",
        )
    assert "ENABLE_DEMO_SEED must be False in production" in str(exc.value)


def test_production_rejects_in_memory_queue():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-production-grade-secret-key-32chars!",
            DEFAULT_LLM_PROVIDER="openai",
            OPENAI_API_KEY="sk-valid-production-key",
            ENABLE_DEMO_SEED=False,
            USE_IN_MEMORY_QUEUE=True,
            STORAGE_TYPE="s3",
        )
    assert "USE_IN_MEMORY_QUEUE cannot be True in production" in str(exc.value)


def test_production_rejects_local_storage():
    with pytest.raises(ValidationError) as exc:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-production-grade-secret-key-32chars!",
            DEFAULT_LLM_PROVIDER="openai",
            OPENAI_API_KEY="sk-valid-production-key",
            ENABLE_DEMO_SEED=False,
            USE_IN_MEMORY_QUEUE=False,
            STORAGE_TYPE="local",
        )
    assert "STORAGE_TYPE must be 's3' in production" in str(exc.value)


def test_production_rejects_placeholder_secrets():
    for bad_secret in [
        "change-me-locally-with-a-very-long-key-string",
        "generate-a-long-random-secret-key-at-least-32-chars",
        "insecure-dev-secret-key-change-in-production-opspilot-2026",
    ]:
        with pytest.raises(ValidationError) as exc:
            Settings(
                ENVIRONMENT="production",
                SECRET_KEY=bad_secret,
                DEFAULT_LLM_PROVIDER="openai",
                OPENAI_API_KEY="sk-valid-production-key",
                ENABLE_DEMO_SEED=False,
                USE_IN_MEMORY_QUEUE=False,
                STORAGE_TYPE="s3",
            )
        assert "cannot contain default placeholders" in str(exc.value)
