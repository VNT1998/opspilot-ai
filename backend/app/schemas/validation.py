from typing import Any, List, Optional
from pydantic import BaseModel


class ValidationFinding(BaseModel):
    rule_name: str
    passed: bool
    severity: str  # ERROR, WARNING, INFO
    message: str
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None


class BusinessValidationResult(BaseModel):
    is_clean: bool
    confidence_score: float
    variance_amount: float
    variance_percent: float
    requires_human_review: bool
    routing_reason: Optional[str] = None
    findings: List[ValidationFinding]
