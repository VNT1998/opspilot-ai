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
        actor_id="usr_admin_1",
    )
    # Second identical call for same document
    inv2 = await erp.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_test_idem",
        invoice_number="INV-IDEM-001",
        vendor_name="Acme Industrial Supplies",
        total_amount=1450.00,
        actor_id="usr_admin_1",
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
        actor_id="usr_admin_1",
    )
    # Attempt to post invoice with same invoice number for document B -> ConflictError
    with pytest.raises(ConflictError) as exc_info:
        await erp.post_invoice(
            tenant_id="tenant_test",
            document_id="doc_b_200",
            invoice_number="INV-DUP-999",
            vendor_name="Acme Industrial Supplies",
            total_amount=1450.00,
            actor_id="usr_admin_1",
        )
    assert "Duplicate invoice detected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_audit_chain_verification_and_tamper_detection(db_session: AsyncSession):
    """AuditLog hash chaining is cryptographic and detects tampering."""
    from app.services.audit.service import AuditService
    from app.models.audit import AuditLog

    tenant_id = "tenant_audit_test"

    # Log 3 events
    await AuditService.log_event(
        db=db_session,
        tenant_id=tenant_id,
        action="DOC_CREATE",
        entity_type="Document",
        entity_id="doc_1",
        user_id="usr_1",
        commit=True,
    )
    await AuditService.log_event(
        db=db_session,
        tenant_id=tenant_id,
        action="DOC_PROCESS",
        entity_type="Document",
        entity_id="doc_1",
        user_id="usr_1",
        commit=True,
    )
    await AuditService.log_event(
        db=db_session,
        tenant_id=tenant_id,
        action="INVOICE_POST",
        entity_type="Invoice",
        entity_id="inv_1",
        user_id="usr_1",
        commit=True,
    )

    # Valid chain passes verification
    is_valid = await AuditService.verify_chain(db_session, tenant_id)
    assert is_valid is True

    # Tamper with event 2 in the database
    stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id, AuditLog.action == "DOC_PROCESS")
    second_log = (await db_session.execute(stmt)).scalar_one()
    second_log.action = "DOC_TAMPERED"
    await db_session.commit()

    # Chain verification now fails
    is_valid_after_tamper = await AuditService.verify_chain(db_session, tenant_id)
    assert is_valid_after_tamper is False


@pytest.mark.asyncio
async def test_transaction_rollback_leaves_no_side_effects(db_session: AsyncSession):
    """Rollback after ERP flush leaves no invoice or audit rows persisted."""
    from app.models.erp import Invoice
    from app.models.audit import AuditLog

    erp = ERPService(db_session)
    tenant_id = "tenant_rollback_test"
    doc_id = "doc_rollback_1"

    # Post invoice with commit=False (flushes only)
    await erp.post_invoice(
        tenant_id=tenant_id,
        document_id=doc_id,
        invoice_number="INV-ROLLBACK-001",
        vendor_name="Acme Supplies",
        total_amount=100.00,
        actor_id="usr_1",
        commit=False,
    )

    # Simulate unexpected route failure right after ERP post
    await db_session.rollback()

    # Verify neither invoice nor audit log was committed
    inv_check = (
        await db_session.execute(select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.document_id == doc_id))
    ).scalar_one_or_none()
    assert inv_check is None

    audit_check = (await db_session.execute(select(AuditLog).where(AuditLog.tenant_id == tenant_id))).scalars().all()
    assert len(audit_check) == 0


@pytest.mark.asyncio
async def test_unique_constraint_on_tenant_and_document_id(db_session: AsyncSession):
    """Database enforces unique constraint on (tenant_id, document_id)."""
    from decimal import Decimal
    from sqlalchemy.exc import IntegrityError
    from app.models.erp import Invoice

    tenant_id = "tenant_uq_test"
    doc_id = "doc_uq_1"

    inv1 = Invoice(
        tenant_id=tenant_id,
        document_id=doc_id,
        invoice_number="INV-UQ-001",
        vendor_name="Acme",
        total_amount=Decimal("100.00"),
    )
    db_session.add(inv1)
    await db_session.commit()

    # Attempt to insert second invoice with different invoice_number but same document_id
    inv2 = Invoice(
        tenant_id=tenant_id,
        document_id=doc_id,
        invoice_number="INV-UQ-002",
        vendor_name="Acme",
        total_amount=Decimal("200.00"),
    )
    db_session.add(inv2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
