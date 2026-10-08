from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.services.erp.service import ERPService


@pytest.mark.asyncio
async def test_duplicate_invoice_number_raises_conflict(db_session: AsyncSession):
    """Attempting to post the same invoice number for a tenant raises ConflictError cleanly."""
    erp_service = ERPService(db_session)

    # First post succeeds
    inv1 = await erp_service.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_conc_1",
        invoice_number="INV-CONC-001",
        vendor_name="Acme Corp",
        total_amount=Decimal("1500.00"),
        actor_id="user_123",
    )
    assert inv1.id is not None
    await db_session.commit()

    # Second post with same invoice number but different document must raise ConflictError
    with pytest.raises(ConflictError, match="Duplicate invoice detected"):
        await erp_service.post_invoice(
            tenant_id="tenant_test",
            document_id="doc_conc_2",
            invoice_number="INV-CONC-001",
            vendor_name="Acme Corp",
            total_amount=Decimal("1500.00"),
            actor_id="user_123",
        )


@pytest.mark.asyncio
async def test_document_idempotency_returns_existing_invoice(db_session: AsyncSession):
    """Posting the exact same document ID again returns existing invoice idempotently."""
    erp_service = ERPService(db_session)

    inv1 = await erp_service.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_idemp_1",
        invoice_number="INV-IDEMP-001",
        vendor_name="Acme Corp",
        total_amount=Decimal("2000.00"),
        actor_id="user_123",
    )
    await db_session.commit()

    # Repeat with same document ID
    inv2 = await erp_service.post_invoice(
        tenant_id="tenant_test",
        document_id="doc_idemp_1",
        invoice_number="INV-IDEMP-001",
        vendor_name="Acme Corp",
        total_amount=Decimal("2000.00"),
        actor_id="user_123",
    )
    assert inv1.id == inv2.id
