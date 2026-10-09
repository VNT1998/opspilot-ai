from datetime import datetime
from enum import Enum
import uuid
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"


class DocumentOutbox(Base, TenantScopedMixin, TimestampMixin):
    """
    Persistent transactional outbox for document ingestion and workflow execution dispatch.
    Ensures that document uploads never diverge from job queue delivery.
    """

    __tablename__ = "document_outbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"ob_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=OutboxStatus.PENDING.value, index=True, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship("Document")  # noqa: F821
    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun")  # noqa: F821
