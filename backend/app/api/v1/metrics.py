from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
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
    """Calculates operational and economic telemetry KPIs using truthful database aggregation."""
    # 1. Total documents & status breakdown via database-side GROUP BY
    status_stmt = (
        select(Document.status, func.count(Document.id))
        .where(Document.tenant_id == current_user.tenant_id)
        .group_by(Document.status)
    )
    status_rows = (await db.execute(status_stmt)).all()
    status_counts = {r[0]: r[1] for r in status_rows}
    total_docs = sum(status_counts.values())
    status_breakdown = [StatusBreakdown(status=k, count=v) for k, v in status_counts.items()]

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_stmt = select(func.count(Document.id)).where(
        Document.tenant_id == current_user.tenant_id, Document.created_at >= today_start
    )
    docs_today = (await db.execute(today_stmt)).scalar() or 0

    completed_docs = status_counts.get("COMPLETED", 0)
    approved_docs = status_counts.get("APPROVED", 0)
    auto_rate = round((completed_docs / total_docs * 100.0), 1) if total_docs > 0 else 0.0

    # 2. Review queue size
    rev_stmt = select(func.count(ReviewTask.id)).where(
        ReviewTask.tenant_id == current_user.tenant_id,
        ReviewTask.status == "PENDING",
    )
    rev_count = (await db.execute(rev_stmt)).scalar() or 0

    # 3. Average confidence score via SQL - NO FAKE 0.94 FALLBACK
    conf_stmt = select(func.avg(Document.confidence_score)).where(
        Document.tenant_id == current_user.tenant_id,
        Document.confidence_score.isnot(None),
    )
    avg_conf_raw = (await db.execute(conf_stmt)).scalar()
    avg_conf = round(float(avg_conf_raw), 2) if avg_conf_raw is not None else 0.0

    # 4. Exception rate
    exception_docs_count = sum(status_counts.get(s, 0) for s in ("REVIEW_REQUIRED", "REJECTED", "FAILED"))
    exc_rate = round((exception_docs_count / total_docs * 100.0), 1) if total_docs > 0 else 0.0

    # 5. Economic savings: 0.25h saved per resolved/approved document
    hours_saved = round((completed_docs + approved_docs) * 0.25, 2)

    # 6. Truthful agent telemetry tokens, costs, and latency
    agent_stmt = select(
        func.coalesce(func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0),
        func.coalesce(func.sum(AgentRun.total_cost), 0.0),
        func.coalesce(func.avg(AgentRun.duration_ms), 0.0),
        func.coalesce(
            func.sum(
                case((AgentRun.usage_source == "provider", AgentRun.input_tokens + AgentRun.output_tokens), else_=0)
            ),
            0,
        ),
        func.coalesce(
            func.sum(
                case((AgentRun.usage_source == "estimated", AgentRun.input_tokens + AgentRun.output_tokens), else_=0)
            ),
            0,
        ),
    ).where(AgentRun.tenant_id == current_user.tenant_id)
    agent_res = (await db.execute(agent_stmt)).first()

    total_tokens = int(agent_res[0]) if agent_res else 0
    total_cost = round(float(agent_res[1]), 4) if agent_res else 0.0
    avg_latency = round(float(agent_res[2]), 1) if agent_res else 0.0
    provider_tokens = int(agent_res[3]) if agent_res else 0
    estimated_tokens = int(agent_res[4]) if agent_res else 0

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
        provider_tokens=provider_tokens,
        estimated_tokens=estimated_tokens,
        calculated_cost=total_cost,
        status_breakdown=status_breakdown,
    )
