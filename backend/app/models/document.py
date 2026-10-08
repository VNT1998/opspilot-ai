from __future__ import annotations

from typing import TYPE_CHECKING
import uuid
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.extraction import DocumentExtraction
    from app.models.review import ReviewTask
    from app.models.workflow import WorkflowRun


class Document(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)

    # Workflow lifecycle status
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", index=True, nullable=False)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    pages: Mapped[list["DocumentPage"]] = relationship(
        "DocumentPage", back_populates="document", cascade="all, delete-orphan"
    )
    extraction: Mapped["DocumentExtraction"] = relationship(
        "DocumentExtraction", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )  # noqa: F821
    review_tasks: Mapped[list["ReviewTask"]] = relationship(
        "ReviewTask", back_populates="document", cascade="all, delete-orphan"
    )  # noqa: F821
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun", back_populates="document", cascade="all, delete-orphan"
    )  # noqa: F821


class DocumentPage(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_pages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"page_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="pages")
