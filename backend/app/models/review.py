import uuid
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin


class ReviewTask(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"rev_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(50), default="PENDING", index=True, nullable=False
    )  # PENDING, RESOLVED, REJECTED
    priority: Mapped[str] = mapped_column(
        String(50), default="MEDIUM", index=True, nullable=False
    )  # LOW, MEDIUM, HIGH, URGENT
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="review_tasks")  # noqa: F821
    actions: Mapped[list["ReviewAction"]] = relationship(
        "ReviewAction", back_populates="review_task", cascade="all, delete-orphan"
    )


class ReviewAction(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "review_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"act_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    review_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("review_tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # APPROVE, REJECT, EDIT, REQUEST_INFO
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_diffs: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON representation of changed fields

    review_task: Mapped["ReviewTask"] = relationship("ReviewTask", back_populates="actions")
