import io
from typing import List
from pypdf import PdfReader
from app.core.errors import ValidationError
from app.services.parsing.result import ParsedDocument, ParsedPage


class PDFDocumentParser:
    """Parser for PDF files using pypdf."""

    async def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as e:
            raise ValidationError(f"Invalid or corrupted PDF file '{filename}': {str(e)}")

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ValidationError(f"PDF document '{filename}' is password-protected and cannot be parsed.")

        pages: List[ParsedPage] = []
        warnings: List[str] = []

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ValidationError(f"PDF document '{filename}' contains 0 pages.")

        for idx, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                cleaned = page_text.strip()
                if not cleaned:
                    warnings.append(f"Page {idx} contained no extractable text layer (possible scan).")
                pages.append(ParsedPage(page_number=idx, text=cleaned, confidence=0.95 if cleaned else 0.0))
            except Exception as e:
                warnings.append(f"Page {idx} extraction failed: {str(e)}")
                pages.append(ParsedPage(page_number=idx, text="", confidence=0.0))

        all_text = "\n\n".join(p.text for p in pages if p.text)
        if not all_text.strip():
            warnings.append("Document appears to be a scanned image with no embedded text layer.")

        return ParsedDocument(
            text=all_text,
            pages=pages,
            parser="PDFDocumentParser",
            parser_version="1.0.0",
            extraction_warnings=warnings,
        )
