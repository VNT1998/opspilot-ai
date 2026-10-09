from dataclasses import dataclass
from typing import Dict, Literal
from pydantic import BaseModel


@dataclass(frozen=True)
class ModelPricing:
    input_rate_per_1k: float
    output_rate_per_1k: float


MODEL_PRICING: Dict[str, ModelPricing] = {
    # OpenAI Models
    "gpt-4o-mini": ModelPricing(input_rate_per_1k=0.00015, output_rate_per_1k=0.00060),
    "gpt-4o": ModelPricing(input_rate_per_1k=0.0025, output_rate_per_1k=0.0100),
    "text-embedding-3-small": ModelPricing(input_rate_per_1k=0.00002, output_rate_per_1k=0.0),
    # Ollama / Self-hosted models (zero external cloud billing)
    "medgemma:4b": ModelPricing(input_rate_per_1k=0.0, output_rate_per_1k=0.0),
    "phi4-mini:latest": ModelPricing(input_rate_per_1k=0.0, output_rate_per_1k=0.0),
    "granite4.1:3b": ModelPricing(input_rate_per_1k=0.0, output_rate_per_1k=0.0),
    "qwen3.5:4b": ModelPricing(input_rate_per_1k=0.0, output_rate_per_1k=0.0),
    # Deterministic Mock
    "mock-agent-v1": ModelPricing(input_rate_per_1k=0.00015, output_rate_per_1k=0.00060),
}

DEFAULT_MODEL_PRICING = ModelPricing(input_rate_per_1k=0.00015, output_rate_per_1k=0.00060)


def calculate_call_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, DEFAULT_MODEL_PRICING)
    cost = (input_tokens / 1000.0) * pricing.input_rate_per_1k + (output_tokens / 1000.0) * pricing.output_rate_per_1k
    return round(cost, 6)


class LLMUsageResult(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    usage_source: Literal["provider", "estimated"]
    latency_ms: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return self.cost
