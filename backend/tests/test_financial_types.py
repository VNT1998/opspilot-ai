from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.erp import Invoice, PurchaseOrder, PurchaseOrderLine, Vendor


@pytest.mark.asyncio
async def test_financial_decimal_precision(db_session: AsyncSession):
    """Ensure database stores and retrieves financial amounts as exact Decimal without float drift."""
    vendor = Vendor(
        id="vnd_dec_1",
        tenant_id="tenant_test",
        name="Precision Corp",
        vendor_code="PREC-001",
    )
    db_session.add(vendor)
    await db_session.flush()

    po = PurchaseOrder(
        id="po_dec_1",
        tenant_id="tenant_test",
        po_number="PO-DEC-001",
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        total_amount=Decimal("12345.67"),
    )
    po.lines.append(
        PurchaseOrderLine(
            tenant_id="tenant_test",
            line_number=1,
            description="Item 1",
            quantity=10.0,
            unit_price=Decimal("1234.56"),
            total_price=Decimal("12345.60"),
        )
    )
    db_session.add(po)

    inv = Invoice(
        id="inv_dec_1",
        tenant_id="tenant_test",
        invoice_number="INV-DEC-001",
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        total_amount=Decimal("12345.67"),
        variance_amount=Decimal("0.07"),
        variance_percent=Decimal("0.01"),
    )
    db_session.add(inv)
    await db_session.commit()

    # Query back
    stmt = select(Invoice).where(Invoice.id == "inv_dec_1")
    res = await db_session.execute(stmt)
    saved_inv = res.scalar_one()

    assert isinstance(saved_inv.total_amount, Decimal)
    assert saved_inv.total_amount == Decimal("12345.67")
    assert isinstance(saved_inv.variance_amount, Decimal)
    assert saved_inv.variance_amount == Decimal("0.07")

    stmt_po = select(PurchaseOrder).where(PurchaseOrder.id == "po_dec_1")
    saved_po = (await db_session.execute(stmt_po)).scalar_one()
    assert isinstance(saved_po.total_amount, Decimal)
    assert saved_po.total_amount == Decimal("12345.67")
