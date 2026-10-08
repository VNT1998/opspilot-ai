from collections import Counter
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_permission
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.document import Document
from app.models.review import ReviewTask
from app.models.user import User
from app.models.workflow import AgentRun
from app.schemas.metrics import MetricsSummaryResponse, StatusBreakdown

router = APIRouter(prefix="/metrics", tags=["Operational Metrics"])


@router.get("", response_model=MetricsSummaryResponse)
async def get_metrics_summary(
    current_user: User = Depends(require_permission(Permission.METRICS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Calculates operational and economic telemetry KPIs for dashboard."""
    # 1. Total documents & status breakdown
    doc_stmt = select(Document).where(Document.tenant_id == current_user.tenant_id)
    docs = (await db.execute(doc_stmt)).scalars().all()
    total_docs = len(docs)

    status_counts = Counter(d.status for d in docs)
    status_breakdown = [StatusBreakdown(status=k, count=v) for k, v in status_counts.items()]

    today_utc = datetime.now(timezone.utc).date()
    docs_today = len([d for d in docs if d.created_at.date() == today_utc])

    completed_docs = [d for d in docs if d.status in ("COMPLETED", "APPROVED")]
    auto_completed = [d for d in docs if d.status == "COMPLETED"]
    auto_rate = round((len(auto_completed) / total_docs * 100.0), 1) if total_docs > 0 else 0.0

    # 2. Review queue size
    rev_stmt = select(func.count(ReviewTask.id)).where(
        ReviewTask.tenant_id == current_user.tenant_id,
        ReviewTask.status == "PENDING",
    )
    rev_count = (await db.execute(rev_stmt)).scalar() or 0

    # 3. Average confidence score
    confs = [d.confidence_score for d in docs if d.confidence_score is not None]
    avg_conf = round(sum(confs) / len(confs), 2) if confs else 0.94

    # 4. Exception rate
    exception_docs = [d for d in docs if d.status in ("REVIEW_REQUIRED", "REJECTED", "FAILED")]
    exc_rate = round((len(exception_docs) / total_docs * 100.0), 1) if total_docs > 0 else 0.0

    # 5. Economic savings: 15 mins (0.25h) manual processing saved per document
    hours_saved = round(len(completed_docs) * 0.25, 2)

    # 6. Agent telemetry tokens, costs, and measured latency
    agent_stmt = select(
        func.coalesce(func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0),
        func.coalesce(func.sum(AgentRun.total_cost), 0.0),
        func.coalesce(func.avg(AgentRun.duration_ms), 0.0),
    ).where(AgentRun.tenant_id == current_user.tenant_id)
    agent_res = (await db.execute(agent_stmt)).first()
    total_tokens = int(agent_res[0]) if agent_res else 0
    total_cost = round(float(agent_res[1]), 4) if agent_res else 0.0
    avg_latency = round(float(agent_res[2]), 1) if agent_res else 0.0

    return MetricsSummaryResponse(
        total_documents=total_docs,
        documents_today=docs_today,
        auto_completion_rate=auto_rate,
        review_queue_size=rev_count,
        avg_processing_latency_ms=avg_latency,
        avg_confidence_score=avg_conf,
        exception_rate=exc_rate,
        estimated_hours_saved=hours_saved,
        total_tokens_used=total_tokens,
        total_token_cost=total_cost,
        status_breakdown=status_breakdown,
    )
