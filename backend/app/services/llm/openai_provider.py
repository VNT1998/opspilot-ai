import json
from typing import Dict, List, Tuple, Type, TypeVar
import httpx
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.errors import AIProviderError

settings = get_settings()
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    """Production OpenAI API provider using httpx async client."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL
        self.base_url = "https://api.openai.com/v1"

    async def generate(self, prompt: str, system: str = "") -> str:
        if not self.api_key:
            raise AIProviderError("OpenAI API key is missing", provider="openai")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0.2},
            )
            if response.status_code != 200:
                raise AIProviderError(f"OpenAI error: {response.text}", provider="openai")
            data = response.json()
            # Capture usage telemetry if present
            if "usage" in data:
                u = data["usage"]
                self.last_usage = {
                    "provider": "openai",
                    "model": self.model,
                    "input_tokens": u.get("prompt_tokens", 0),
                    "output_tokens": u.get("completion_tokens", 0),
                    "total_tokens": u.get("total_tokens", 0),
                    "usage_source": "provider",
                }
            return data["choices"][0]["message"]["content"]

    async def classify_document(self, text: str, filename: str) -> Tuple[str, float]:
        prompt = (
            f"Classify this document based on filename: '{filename}' and content excerpt: '{text[:1000]}'. "
            'Output valid JSON: {"classification": "invoice"|"purchase_order"|"contract"|"receipt"|"other", "confidence": 0.95}'
        )
        out = await self.generate(prompt)
        try:
            data = json.loads(out)
            cls_val = data.get("classification")
            if not cls_val:
                raise ValueError("Missing 'classification' key in JSON response.")
            return (str(cls_val), float(data.get("confidence", 0.90)))
        except Exception as e:
            raise AIProviderError(f"Malformed classification response from OpenAI: {str(e)}", provider="openai")

    async def extract_structured(self, text: str, schema: Type[T]) -> Tuple[T, Dict[str, float]]:
        prompt = (
            f"Extract structured document information adhering to JSON schema: {schema.model_json_schema()}.\n"
            f"Document text:\n{text}\n\nReturn raw JSON only."
        )
        out = await self.generate(prompt)
        try:
            parsed_json = json.loads(out)
            obj = schema.model_validate(parsed_json)
            # Confidences based on validation success
            confidences = {k: 0.95 for k in parsed_json.keys()}
            return (obj, confidences)
        except Exception as e:
            raise AIProviderError(f"Structured extraction validation failed: {str(e)}", provider="openai")

    async def embed(self, text: str) -> List[float]:
        if not self.api_key:
            raise AIProviderError("OpenAI API key is missing", provider="openai")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.embedding_model, "input": text[:8000]},
            )
            if response.status_code != 200:
                raise AIProviderError(f"OpenAI embedding error: {response.text}", provider="openai")
            return response.json()["data"][0]["embedding"]
