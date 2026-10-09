from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class OpsPilotState(TypedDict, total=False):
    tenant_id: str
    user_id: str
    user_role: str
    document_id: str
    workflow_run_id: str
    filename: str
    file_type: str
    raw_text: str

    # Agent step outputs
    classification: str
    classification_confidence: float

    extracted_data: Dict[str, Any]
    field_confidences: Dict[str, float]

    validation_result: Dict[str, Any]
    policy_citations: List[Dict[str, Any]]

    decision: str  # APPROVE_AUTOMATICALLY, SEND_TO_REVIEW, REJECT
    decision_reason: str

    # Side-effect references
    review_task_id: Optional[str]
    invoice_id: Optional[str]

    # Telemetry
    logs: List[str]
    tool_calls_executed: List[Dict[str, Any]]
    model: str
    provider: str
    usage_source: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost: float
