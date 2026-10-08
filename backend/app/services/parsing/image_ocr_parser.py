import io
from typing import List
from PIL import Image
from app.core.errors import ValidationError
from app.services.parsing.result import ParsedDocument, ParsedPage


class ImageOCRParser:
    """Parser and OCR processor for image files (PNG, JPG, JPEG)."""

    async def parse(self, content: bytes, filename: str) -> ParsedDocument:
        try:
            img = Image.open(io.BytesIO(content))
            img.verify()  # Verify valid image bytes
            img = Image.open(io.BytesIO(content))  # Reopen after verify
        except Exception as e:
            raise ValidationError(f"Invalid or corrupted image file '{filename}': {str(e)}")

        # Dimensions check
        width, height = img.size
        warnings: List[str] = []

        extracted_text = ""
        confidence = 0.50

        # Attempt optical character recognition if pytesseract is available
        try:
            import pytesseract
            extracted_text = pytesseract.image_to_string(img).strip()
            confidence = 0.90 if extracted_text else 0.40
        except (ImportError, Exception) as ocr_err:
            warnings.append(
                f"OCR engine pytesseract unavailable or failed ({str(ocr_err)}). "
                f"Image dimensions {width}x{height} verified; routing to human review."
            )

        pages = [
            ParsedPage(
                page_number=1,
                text=extracted_text,
                confidence=confidence,
            )
        ]

        return ParsedDocument(
            text=extracted_text,
            pages=pages,
            parser="ImageOCRParser",
            parser_version="1.0.0",
            extraction_warnings=warnings,
        )
