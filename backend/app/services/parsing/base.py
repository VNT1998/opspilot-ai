from typing import Protocol, runtime_checkable
from app.services.parsing.result import ParsedDocument


@runtime_checkable
class DocumentParser(Protocol):
    """Protocol for document parsing strategies."""

    async def parse(self, content: bytes, filename: str) -> ParsedDocument:
        """Parses raw document bytes and returns structured, page-aware text."""
        ...
