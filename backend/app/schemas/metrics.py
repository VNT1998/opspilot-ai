from typing import Dict, List
from pydantic import BaseModel


class StatusBreakdown(BaseModel):
    status: str
    count: int


class MetricsSummaryResponse(BaseModel):
    total_documents: int
    documents_today: int
    auto_completion_rate: float
    review_queue_size: int
    avg_processing_latency_ms: float
    avg_confidence_score: float
    exception_rate: float
    estimated_hours_saved: float
    total_tokens_used: int
    total_token_cost: float
    status_breakdown: List[StatusBreakdown]
