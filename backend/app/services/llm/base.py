from typing import Dict, List, Protocol, Tuple, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    async def generate(self, prompt: str, system: str = "") -> str:
        """Generates natural language text given a prompt and system instruction."""
        ...

    async def extract_structured(self, text: str, schema: Type[T]) -> Tuple[T, Dict[str, float]]:
        """
        Extracts structured data adhering to a Pydantic schema from input document text.
        Returns a tuple of (extracted_pydantic_instance, field_confidence_scores_map).
        """
        ...

    async def embed(self, text: str) -> List[float]:
        """Generates a dense vector embedding for semantic search."""
        ...

    async def classify_document(self, text: str, filename: str) -> Tuple[str, float]:
        """
        Classifies document into a category (e.g. invoice, purchase_order, contract, receipt).
        Returns tuple of (document_type, confidence_score).
        """
        ...
