from typing import Dict, Generic, List, Protocol, Tuple, Type, TypeVar
from pydantic import BaseModel
from app.services.llm.pricing import LLMUsageResult

T = TypeVar("T", bound=BaseModel)


class ClassificationResult:
    """Typed result holding document classification, confidence score, and per-call LLM usage."""

    def __init__(self, doc_type: str, confidence: float, usage: LLMUsageResult):
        self.doc_type = doc_type
        self.confidence = confidence
        self.usage = usage

    def __iter__(self):
        yield self.doc_type
        yield self.confidence

    def __getitem__(self, index):
        return (self.doc_type, self.confidence)[index]


class ExtractionResult(Generic[T]):
    """Typed result holding extracted Pydantic schema, field confidence map, and per-call LLM usage."""

    def __init__(self, data: T, field_confidences: Dict[str, float], usage: LLMUsageResult):
        self.data = data
        self.field_confidences = field_confidences
        self.usage = usage

    def __iter__(self):
        yield self.data
        yield self.field_confidences

    def __getitem__(self, index):
        return (self.data, self.field_confidences)[index]


class GenerateResult(str):
    """String subclass transparently carrying per-call LLM usage telemetry."""

    usage: LLMUsageResult

    def __new__(cls, text: str, usage: LLMUsageResult):
        obj = str.__new__(cls, text)
        obj.usage = usage
        return obj


class LLMProvider(Protocol):
    async def generate(self, prompt: str, system: str = "") -> str:
        """Generates natural language text given a prompt and system instruction."""
        ...

    async def extract_structured(self, text: str, schema: Type[T]) -> Tuple[T, Dict[str, float]]:
        """
        Extracts structured data adhering to a Pydantic schema from input document text.
        Returns a tuple/ExtractionResult of (extracted_pydantic_instance, field_confidence_scores_map).
        """
        ...

    async def embed(self, text: str) -> List[float]:
        """Generates a dense vector embedding for semantic search."""
        ...

    async def classify_document(self, text: str, filename: str) -> Tuple[str, float]:
        """
        Classifies document into a category (e.g. invoice, purchase_order, contract, receipt).
        Returns tuple/ClassificationResult of (document_type, confidence_score).
        """
        ...
