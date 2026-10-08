import uuid
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin


class WorkflowRun(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", index=True, nullable=False)  # PENDING, RUNNING, REVIEW_REQUIRED, APPROVED, REJECTED, COMPLETED, FAILED
    current_step: Mapped[str] = mapped_column(String(100), default="intake", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="workflow_runs")  # noqa: F821
    steps: Mapped[list["WorkflowStep"]] = relationship("WorkflowStep", back_populates="workflow_run", cascade="all, delete-orphan")
    agent_runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="workflow_run", cascade="all, delete-orphan")


class WorkflowStep(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflow_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"step_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS", nullable=False)  # SUCCESS, FAILED, PAUSED, SKIPPED
    input_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="steps")


class AgentRun(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"ar_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    workflow_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="agent_runs")
    tool_calls: Mapped[list["ToolCall"]] = relationship("ToolCall", back_populates="agent_run", cascade="all, delete-orphan")


class ToolCall(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"tc_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS", nullable=False)  # SUCCESS, FAILED, DENIED
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    agent_run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="tool_calls")
