from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import require_permission
from app.core.errors import NotFoundError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.user import User
from app.models.workflow import AgentRun, WorkflowRun
from app.schemas.agent import WorkflowRunResponse

router = APIRouter(prefix="/agent", tags=["Agent Orchestration"])


@router.get("/runs", response_model=List[WorkflowRunResponse])
async def list_agent_runs(
    current_user: User = Depends(require_permission(Permission.AGENT_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Lists agent workflow runs and traces."""
    stmt = (
        select(WorkflowRun)
        .options(
            selectinload(WorkflowRun.steps),
            selectinload(WorkflowRun.agent_runs).selectinload(AgentRun.tool_calls),
        )
        .where(WorkflowRun.tenant_id == current_user.tenant_id)
        .order_by(desc(WorkflowRun.created_at))
        .limit(50)
    )
    res = await db.execute(stmt)
    runs = res.scalars().all()
    return [WorkflowRunResponse.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_agent_run(
    run_id: str,
    current_user: User = Depends(require_permission(Permission.AGENT_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves step-by-step trace and tool calls for a specific workflow execution."""
    stmt = (
        select(WorkflowRun)
        .options(
            selectinload(WorkflowRun.steps),
            selectinload(WorkflowRun.agent_runs).selectinload(AgentRun.tool_calls),
        )
        .where(WorkflowRun.id == run_id, WorkflowRun.tenant_id == current_user.tenant_id)
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run:
        raise NotFoundError("WorkflowRun", run_id)

    return WorkflowRunResponse.model_validate(run)
