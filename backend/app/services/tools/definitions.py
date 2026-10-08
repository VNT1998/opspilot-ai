from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ToolPermission(str, Enum):
    READ_DOCUMENT = "document:read"
    READ_PO = "document:read"
    READ_POLICY = "knowledge:search"
    READ_VENDOR = "document:read"
    CALCULATE_VARIANCE = "document:read"
    CREATE_REVIEW_TASK = "review:edit"
    UPDATE_INVOICE = "review:approve"
    SEND_NOTIFICATION = "document:read"


class ToolCallContext(BaseModel):
    tenant_id: str
    user_id: Optional[str] = "agent_system"
    user_role: str = "admin"  # Role executed under


class GetDocumentInput(BaseModel):
    document_id: str = Field(..., description="The unique document ID")


class GetPurchaseOrderInput(BaseModel):
    po_number: str = Field(..., description="Purchase order number")


class SearchPolicyInput(BaseModel):
    query: str = Field(..., description="Policy question or search term")


class GetVendorInput(BaseModel):
    vendor_name: str = Field(..., description="Vendor name or code")


class CalculateVarianceInput(BaseModel):
    invoice_total: float = Field(..., description="Total invoice amount")
    po_total: float = Field(..., description="Purchase order total amount")


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
