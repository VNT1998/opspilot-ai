from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_permission
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit-logs", tags=["Audit & Governance"])


@router.get("", response_model=List[AuditLogResponse])
async def list_audit_logs(
    current_user: User = Depends(require_permission(Permission.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Lists immutable audit log entries for regulatory compliance and operational traceability."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == current_user.tenant_id)
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)

    res = await db.execute(stmt)
    logs = res.scalars().all()
    return [AuditLogResponse.model_validate(l) for l in logs]
