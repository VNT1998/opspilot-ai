import re
from typing import List
from app.core.errors import ValidationError
from app.services.parsing.result import ParsedDocument, ParsedPage


class TextDocumentParser:
    """Parser for raw UTF-8 / ASCII text documents."""

    async def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                raise ValidationError(f"Unable to decode text document '{filename}': {str(e)}")

        # Check for explicit page markers or form feed
        raw_pages = re.split(r"(?:---+\s*Page\s*\d+\s*---+|\x0c)", text)
        pages: List[ParsedPage] = []

        page_num = 1
        for p in raw_pages:
            cleaned = p.strip()
            if cleaned:
                pages.append(ParsedPage(page_number=page_num, text=cleaned, confidence=1.0))
                page_num += 1

        if not pages:
            pages = [ParsedPage(page_number=1, text=text.strip(), confidence=1.0)]

        normalized_text = "\n\n".join(p.text for p in pages)
        return ParsedDocument(
            text=normalized_text,
            pages=pages,
            parser="TextDocumentParser",
            parser_version="1.0.0",
            extraction_warnings=[],
        )
