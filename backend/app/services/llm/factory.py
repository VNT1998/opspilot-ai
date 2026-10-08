from app.core.config import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.openai_provider import OpenAIProvider

settings = get_settings()


def get_llm_provider() -> LLMProvider:
    """Returns the configured LLM provider instance."""
    if settings.DEFAULT_LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return OpenAIProvider()
    # Default to the robust Mock Provider
    return MockLLMProvider()
