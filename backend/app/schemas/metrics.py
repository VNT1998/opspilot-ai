from typing import List, Optional
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
    avg_confidence_score: Optional[float] = 0.0
    exception_rate: float
    estimated_hours_saved: float
    total_tokens_used: int
    total_token_cost: float
    provider_tokens: Optional[int] = 0
    estimated_tokens: Optional[int] = 0
    calculated_cost: Optional[float] = 0.0
    status_breakdown: List[StatusBreakdown]
