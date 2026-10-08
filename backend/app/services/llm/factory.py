from app.core.config import get_settings
from app.core.errors import AIProviderError
from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.openai_provider import OpenAIProvider

settings = get_settings()


def get_llm_provider() -> LLMProvider:
    """Returns the explicitly configured LLM provider instance.
    Never silently falls back to MockLLMProvider in production."""
    provider_name = settings.DEFAULT_LLM_PROVIDER.lower()

    if settings.ENVIRONMENT == "production":
        if provider_name == "mock":
            raise AIProviderError(
                "MockLLMProvider is strictly prohibited in production.", provider="mock", retryable=False
            )
        if provider_name == "openai":
            if not settings.OPENAI_API_KEY:
                raise AIProviderError(
                    "OPENAI_API_KEY is not configured for OpenAI provider.", provider="openai", retryable=False
                )
            return OpenAIProvider()
        raise AIProviderError(
            f"Unsupported or unconfigured LLM provider in production: {provider_name}",
            provider=provider_name,
            retryable=False,
        )

    # Development / Testing environment
    if provider_name == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider()
    return MockLLMProvider()
