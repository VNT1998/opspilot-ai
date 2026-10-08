from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    user_id: Optional[str] = None
    actor_type: str
    action: str
    entity_type: str
    entity_id: str
    before_state: Optional[str] = None
    after_state: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
