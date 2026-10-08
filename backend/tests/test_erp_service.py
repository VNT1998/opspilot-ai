import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models.erp import Invoice
from app.services.erp.service import ERPService


@pytest.mark.asyncio
async def test_erp_service_post_invoice_lifecycle(db_session: AsyncSession):
    erp = ERPService(db_session)
    invoice = await erp.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_test_101",
        invoice_number="INV-ERP-001",
        vendor_name="Acme Industrial Supplies",
        total_amount=1450.00,
        currency="USD",
        po_number="PO-9001",
        source="agent",
        actor_id="usr_admin_1",
    )
    assert invoice.id is not None
    assert invoice.status == "POSTED"
    assert invoice.invoice_number == "INV-ERP-001"


@pytest.mark.asyncio
async def test_erp_service_idempotent_duplicate_call(db_session: AsyncSession):
    erp = ERPService(db_session)
    # First call
    inv1 = await erp.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_test_idem",
        invoice_number="INV-IDEM-001",
        vendor_name="Acme Industrial Supplies",
        total_amount=1450.00,
    )
    # Second identical call for same document
    inv2 = await erp.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_test_idem",
        invoice_number="INV-IDEM-001",
        vendor_name="Acme Industrial Supplies",
        total_amount=1450.00,
    )
    assert inv1.id == inv2.id

    # Verify only 1 invoice exists in the database
    count_stmt = select(Invoice).where(
        Invoice.tenant_id == "tenant_test",
        Invoice.invoice_number == "INV-IDEM-001",
    )
    rows = (await db_session.execute(count_stmt)).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_erp_service_duplicate_invoice_number_conflict(db_session: AsyncSession):
    erp = ERPService(db_session)
    # Post invoice for document A
    await erp.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_a_100",
        invoice_number="INV-DUP-999",
        vendor_name="Acme Industrial Supplies",
        total_amount=1450.00,
    )
    # Attempt to post invoice with same invoice number for document B -> ConflictError
    with pytest.raises(ConflictError) as exc_info:
        await erp.post_invoice(
            tenant_id="tenant_test",
            document_id="doc_b_200",
            invoice_number="INV-DUP-999",
            vendor_name="Acme Industrial Supplies",
            total_amount=1450.00,
        )
    assert "Duplicate invoice detected" in str(exc_info.value)
