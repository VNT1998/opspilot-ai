import uuid
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin


class KnowledgeDocument(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"kdoc_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(50), default="policy", index=True, nullable=False
    )  # policy, sop, contract
    department: Mapped[str] = mapped_column(String(100), default="finance", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    acl_roles_json: Mapped[str] = mapped_column(
        Text, default='["admin", "ops_manager", "reviewer", "viewer"]', nullable=False
    )

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"kchk_{uuid.uuid4().hex[:12]}")
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded float array
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["KnowledgeDocument"] = relationship("KnowledgeDocument", back_populates="chunks")
