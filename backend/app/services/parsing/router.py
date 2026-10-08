from pathlib import Path
from app.core.errors import ValidationError
from app.services.parsing.base import DocumentParser
from app.services.parsing.docx_parser import DocxDocumentParser
from app.services.parsing.image_ocr_parser import ImageOCRParser
from app.services.parsing.pdf_parser import PDFDocumentParser
from app.services.parsing.result import ParsedDocument
from app.services.parsing.text_parser import TextDocumentParser


class DocumentParserRouter:
    """Routes documents to the appropriate specialized parser based on extension and content."""

    def __init__(self):
        self.text_parser = TextDocumentParser()
        self.pdf_parser = PDFDocumentParser()
        self.docx_parser = DocxDocumentParser()
        self.image_parser = ImageOCRParser()

    def get_parser(self, filename: str) -> DocumentParser:
        ext = Path(filename).suffix.lower()
        if ext in (".txt", ".log", ".csv", ".json"):
            return self.text_parser
        elif ext == ".pdf":
            return self.pdf_parser
        elif ext in (".docx", ".doc"):
            return self.docx_parser
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            return self.image_parser
        else:
            raise ValidationError(f"Unsupported file format '{ext}' for file '{filename}'.")

    async def parse_document(self, content: bytes, filename: str) -> ParsedDocument:
        """Parses document bytes into a structured ParsedDocument."""
        if not content:
            raise ValidationError(f"Document '{filename}' is empty (0 bytes).")
        parser = self.get_parser(filename)
        return await parser.parse(content, filename)


_router_instance = DocumentParserRouter()


def get_document_parser_router() -> DocumentParserRouter:
    return _router_instance
