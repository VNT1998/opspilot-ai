from decimal import Decimal
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from app.core.rbac import Permission


class ToolRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ToolMetadata(BaseModel):
    name: str
    description: str
    required_permissions: List[Permission]
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    side_effect: bool = False
    idempotent: bool = True
    requires_confirmation: bool = False


class ToolCallContext(BaseModel):
    tenant_id: str
    user_id: str
    user_role: str
    permissions: List[str] = Field(default_factory=list)
    request_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    source: str = "agent"


class GetDocumentInput(BaseModel):
    document_id: str = Field(..., description="The unique document ID")


class GetPurchaseOrderInput(BaseModel):
    po_number: str = Field(..., description="Purchase order number")


class SearchPolicyInput(BaseModel):
    query: str = Field(..., description="Policy question or search term")


class GetVendorInput(BaseModel):
    vendor_name: str = Field(..., description="Vendor name or code")


class CalculateVarianceInput(BaseModel):
    invoice_total: Decimal = Field(..., description="Total invoice amount")
    po_total: Decimal = Field(..., description="Purchase order total amount")


class CreateReviewTaskInput(BaseModel):
    document_id: str = Field(..., description="Document ID requiring review")
    reason: str = Field(..., description="Reason for escalating to human review")
    priority: str = Field("MEDIUM", description="Task priority: LOW, MEDIUM, HIGH, URGENT")


class UpdateInvoiceStatusInput(BaseModel):
    invoice_id: str = Field(..., description="Invoice ID to update")
    status: str = Field(..., description="New status: POSTED, REJECTED, ON_HOLD")


class SendNotificationInput(BaseModel):
    recipient_role: str = Field("reviewer", description="Role to notify")
    message: str = Field(..., description="Notification body")
