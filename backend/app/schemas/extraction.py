from datetime import date
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvoiceLineSchema(BaseModel):
    description: str = Field(..., description="Item or service description")
    quantity: float = Field(..., description="Quantity billed")
    unit_price: float = Field(..., description="Price per unit")
    tax: Optional[float] = Field(0.0, description="Tax amount for this line")
    total_price: float = Field(..., description="Line total amount")
    sku: Optional[str] = Field(None, description="SKU or part identifier")


class InvoiceExtractionSchema(BaseModel):
    invoice_number: str = Field(..., description="Unique invoice identifier")
    invoice_date: str = Field(..., description="Invoice issue date in YYYY-MM-DD format")
    vendor_name: str = Field(..., description="Name of the billing vendor")
    currency: str = Field("USD", description="Currency code, e.g. USD, EUR")
    subtotal: float = Field(..., description="Subtotal before taxes")
    tax: float = Field(0.0, description="Total tax applied")
    total: float = Field(..., description="Total invoice amount payable")
    payment_terms: Optional[str] = Field(None, description="Payment terms, e.g. Net 30")
    po_number: Optional[str] = Field(None, description="Referenced Purchase Order number")
    line_items: List[InvoiceLineSchema] = Field(default_factory=list, description="Extracted line items")


import json

class DocumentExtractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    schema_type: str
    structured_data: Dict
    field_confidences: Dict[str, float]
    validation_findings: Optional[List[Dict]] = None
    is_valid: bool

    @field_validator("structured_data", "field_confidences", mode="before")
    @classmethod
    def parse_json_dict(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {}
        return v or {}

    @field_validator("validation_findings", mode="before")
    @classmethod
    def parse_json_list(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v
