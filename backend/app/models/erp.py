import uuid
from decimal import Decimal
from sqlalchemy import Boolean, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TenantScopedMixin, TimestampMixin


class Vendor(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "vendors"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"vnd_{uuid.uuid4().hex[:12]}")
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    vendor_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_terms: Mapped[str] = mapped_column(String(64), default="Net 30", nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PurchaseOrder(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"po_{uuid.uuid4().hex[:12]}")
    po_number: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    vendor_id: Mapped[str] = mapped_column(String(64), ForeignKey("vendors.id"), index=True, nullable=False)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="OPEN", nullable=False)  # OPEN, MATCHED, CLOSED

    lines: Mapped[list["PurchaseOrderLine"]] = relationship("PurchaseOrderLine", back_populates="po", cascade="all, delete-orphan")


class PurchaseOrderLine(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "purchase_order_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"pol_{uuid.uuid4().hex[:12]}")
    po_id: Mapped[str] = mapped_column(String(64), ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True, nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)

    po: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="lines")


class Invoice(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    document_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    vendor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("vendors.id"), nullable=True)
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    po_number: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False)  # DRAFT, POSTED, REJECTED
    variance_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    variance_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(50), default="CLEAN", nullable=False)  # CLEAN, EXCEPTION

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_tenant_invoice_number"),
    )
    lines: Mapped[list["InvoiceLine"]] = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLine(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "invoice_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"invl_{uuid.uuid4().hex[:12]}")
    invoice_id: Mapped[str] = mapped_column(String(64), ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    tax: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="lines")
