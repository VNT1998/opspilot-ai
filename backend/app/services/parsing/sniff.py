from typing import Tuple
from app.core.errors import ValidationError

# Magic signatures: (magic_bytes, mime_type, list_of_matching_extensions, parser_kind)
SIGNATURE_SPECS = [
    (b"%PDF-", "application/pdf", [".pdf"], "pdf"),
    (b"%PDF", "application/pdf", [".pdf"], "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png", [".png"], "image"),
    (b"\xff\xd8\xff", "image/jpeg", [".jpg", ".jpeg"], "image"),
    (b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", [".docx"], "docx"),
]


def sniff_content(content: bytes, filename: str) -> Tuple[str, str]:
    """
    Sniffs file content magic bytes and validates consistency against declared file extension.

    Returns:
        Tuple[str, str]: (detected_mime_type, parser_kind)

    Raises:
        ValidationError: If content is empty, format is unrecognized, or extension mismatches magic bytes.
    """
    if not content:
        raise ValidationError("File content is empty (0 bytes).")

    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    for magic, mime, valid_exts, parser_kind in SIGNATURE_SPECS:
        if content.startswith(magic):
            if ext and ext not in valid_exts:
                raise ValidationError(
                    f"Declared extension '{ext}' does not match detected file signature for {mime} (expected: {valid_exts})."
                )
            return mime, parser_kind

    # Allow plain text if extension is explicitly .txt
    if ext == ".txt":
        try:
            content.decode("utf-8")
            return "text/plain", "text"
        except UnicodeDecodeError:
            raise ValidationError("File declared as .txt contains non-UTF-8 binary data.")

    raise ValidationError("File signature does not match any allowed format. Allowed formats: PDF, PNG, JPEG, DOCX.")
