from typing import List, Optional
from pydantic import BaseModel


class ParsedPage(BaseModel):
    page_number: int
    text: str
    confidence: Optional[float] = None


class ParsedDocument(BaseModel):
    text: str
    pages: List[ParsedPage]
    parser: str
    parser_version: str
    extraction_warnings: List[str] = []
