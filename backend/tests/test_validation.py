import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.extraction import InvoiceExtractionSchema, InvoiceLineSchema
from app.services.validation.engine import ValidationEngine


@pytest.mark.asyncio
async def test_validation_clean_invoice(db_session: AsyncSession):
    engine = ValidationEngine(db_session)
    extraction = InvoiceExtractionSchema(
        invoice_number="INV-CLEAN-01",
        invoice_date="2026-10-01",
        vendor_name="Acme Industrial Supplies",
        currency="USD",
        subtotal=1318.18,
        tax=131.82,
        total=1450.00,
        po_number="PO-9001",
        line_items=[
            InvoiceLineSchema(
                description="Standard Enterprise Service License",
                quantity=1.0,
                unit_price=1318.18,
                total_price=1318.18,
            )
        ],
    )
    confidences = {k: 0.98 for k in ["invoice_number", "total", "subtotal", "tax", "po_number"]}

    result = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=extraction,
        field_confidences=confidences,
    )
    assert result.is_clean is True
    assert result.requires_human_review is False
    assert result.variance_amount == 0.0


@pytest.mark.asyncio
async def test_validation_high_value_threshold(db_session: AsyncSession):
    engine = ValidationEngine(db_session)
    extraction = InvoiceExtractionSchema(
        invoice_number="INV-HIGH-VAL",
        invoice_date="2026-10-01",
        vendor_name="Acme Industrial Supplies",
        currency="USD",
        subtotal=11000.00,
        tax=1000.00,
        total=12000.00,  # Exceeds $10,000 policy threshold
        po_number=None,
    )
    confidences = {k: 0.99 for k in ["invoice_number", "total", "subtotal"]}

    result = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=extraction,
        field_confidences=confidences,
    )
    assert result.requires_human_review is True
    assert any(f.rule_name == "high_value_policy_threshold" for f in result.findings)


@pytest.mark.asyncio
async def test_validation_po_variance_exceeded(db_session: AsyncSession):
    engine = ValidationEngine(db_session)
    # PO-9001 total is $1450.00. Here invoice is $1600.00 (variance > 10%)
    extraction = InvoiceExtractionSchema(
        invoice_number="INV-VAR-01",
        invoice_date="2026-10-01",
        vendor_name="Acme Industrial Supplies",
        currency="USD",
        subtotal=1454.55,
        tax=145.45,
        total=1600.00,
        po_number="PO-9001",
    )
    confidences = {k: 0.95 for k in ["invoice_number", "total", "po_number"]}

    result = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=extraction,
        field_confidences=confidences,
    )
    assert result.requires_human_review is True
    assert result.variance_percent > 2.0
    assert any("PO variance exceeds tolerance" in f.message for f in result.findings)
