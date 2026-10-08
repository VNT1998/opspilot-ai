from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tool_name: str
    input_json: str
    output_json: str
    status: str
    duration_ms: int


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_cost: float
    duration_ms: int
    tool_calls: List[ToolCallResponse] = []


class WorkflowStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_name: str
    status: str
    input_state: Optional[str] = None
    output_state: Optional[str] = None
    latency_ms: int
    error_message: Optional[str] = None


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    document_id: str
    status: str
    current_step: str
    result_summary: Optional[str] = None
    created_at: datetime
    steps: List[WorkflowStepResponse] = []
    agent_runs: List[AgentRunResponse] = []
