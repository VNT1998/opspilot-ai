import json
import time
from typing import Dict, List, Tuple, Type, TypeVar
import httpx
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.errors import AIProviderError
from app.services.llm.base import ClassificationResult, ExtractionResult, GenerateResult
from app.services.llm.pricing import LLMUsageResult, calculate_call_cost

settings = get_settings()
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    """Production OpenAI and OpenAI-compatible API provider (e.g. Ollama/vLLM) using httpx async client."""

    usage_source: str = "provider"
    provider: str = "openai"

    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL
        self.base_url = base_url or settings.OPENAI_BASE_URL or "https://api.openai.com/v1"
        self.last_usage: Dict = {}

    async def generate(self, prompt: str, system: str = "") -> GenerateResult:
        if not self.api_key:
            raise AIProviderError("OpenAI API key is missing", provider="openai")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0.2},
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            if response.status_code != 200:
                raise AIProviderError(f"OpenAI error: {response.text}", provider="openai")
            data = response.json()

            u = data.get("usage", {})
            in_tok = u.get("prompt_tokens", 0)
            out_tok = u.get("completion_tokens", 0)
            tot_tok = u.get("total_tokens", in_tok + out_tok)
            cost = calculate_call_cost(self.model, in_tok, out_tok)

            usage = LLMUsageResult(
                provider="openai",
                model=self.model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                total_tokens=tot_tok,
                cost=cost,
                usage_source="provider",
                latency_ms=elapsed_ms,
            )
            self.last_usage = usage.model_dump()
            content = data["choices"][0]["message"]["content"]
            return GenerateResult(content, usage)

    async def classify_document(self, text: str, filename: str) -> Tuple[str, float]:
        prompt = (
            f"Classify this document based on filename: '{filename}' and content excerpt: '{text[:1000]}'. "
            'Output valid JSON: {"classification": "invoice"|"purchase_order"|"contract"|"receipt"|"other", "confidence": 0.95}'
        )
        gen_res = await self.generate(prompt)
        try:
            data = json.loads(str(gen_res))
            cls_val = data.get("classification")
            if not cls_val:
                raise ValueError("Missing 'classification' key in JSON response.")
            conf_val = float(data.get("confidence", 0.90))
            return ClassificationResult(str(cls_val), conf_val, gen_res.usage)
        except Exception as e:
            raise AIProviderError(f"Malformed classification response from OpenAI: {str(e)}", provider="openai")

    async def extract_structured(self, text: str, schema: Type[T]) -> Tuple[T, Dict[str, float]]:
        prompt = (
            f"Extract structured document information adhering to JSON schema: {schema.model_json_schema()}.\n"
            f"Document text:\n{text}\n\nReturn raw JSON only."
        )
        gen_res = await self.generate(prompt)
        try:
            parsed_json = json.loads(str(gen_res))
            obj = schema.model_validate(parsed_json)
            confidences = {k: 0.95 for k in parsed_json.keys()}
            return ExtractionResult(obj, confidences, gen_res.usage)
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
