from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.extraction import DocumentExtractionResponse


class DocumentPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    page_number: int
    text_content: str
    image_path: Optional[str] = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    filename: str
    file_type: str
    file_size: int
    mime_type: str
    status: str
    classification: Optional[str] = None
    confidence_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    pages: Optional[List[DocumentPageResponse]] = None
    extraction: Optional[DocumentExtractionResponse] = None


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentReprocessRequest(BaseModel):
    force: bool = False
