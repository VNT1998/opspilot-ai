from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.document import DocumentResponse


class ReviewActionRequest(BaseModel):
    action: str  # APPROVE, REJECT, EDIT, REQUEST_INFO
    comments: Optional[str] = None
    edited_fields: Optional[Dict[str, Any]] = None


class ReviewTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    document_id: str
    workflow_run_id: Optional[str] = None
    status: str
    priority: str
    reason: str
    confidence: Optional[float] = None
    assigned_to_user_id: Optional[str] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    document: Optional[DocumentResponse] = None


class ReviewDecisionResponse(BaseModel):
    message: str
    task_id: str
    status: str
    workflow_status: str
