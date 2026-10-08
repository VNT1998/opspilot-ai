import uuid
from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin


class DocumentExtraction(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "document_extractions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"ext_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    schema_type: Mapped[str] = mapped_column(String(50), default="invoice", nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded dictionary of extracted fields
    field_confidences: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded field -> score mapping
    validation_findings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of rule checks
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    document: Mapped["Document"] = relationship("Document", back_populates="extraction")  # noqa: F821
