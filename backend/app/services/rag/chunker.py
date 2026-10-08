import re
from typing import Dict, List


class TextChunk:
    def __init__(self, text: str, chunk_index: int, page_number: int = 1, metadata: Dict | None = None):
        self.text = text
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.metadata = metadata or {}


def chunk_document_text(text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> List[TextChunk]:
    """
    Section-aware sliding-window chunker that splits on paragraphs or sentences
    while maintaining overlap for boundary comprehension.
    """
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks: List[TextChunk] = []
    current_chunk = ""
    chunk_idx = 0
    page_num = 1

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Check for page markers e.g. "--- Page 2 ---"
        page_match = re.search(r"--- Page (\d+) ---", para)
        if page_match:
            page_num = int(page_match.group(1))

        if len(current_chunk) + len(para) < chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(TextChunk(text=current_chunk, chunk_index=chunk_idx, page_number=page_num))
                chunk_idx += 1
                # Retain overlap from end of current chunk
                overlap_text = current_chunk[-chunk_overlap:] if len(current_chunk) > chunk_overlap else ""
                current_chunk = overlap_text + ("\n\n" if overlap_text else "") + para
            else:
                chunks.append(TextChunk(text=para, chunk_index=chunk_idx, page_number=page_num))
                chunk_idx += 1
                current_chunk = ""

    if current_chunk:
        chunks.append(TextChunk(text=current_chunk, chunk_index=chunk_idx, page_number=page_num))

    return chunks
