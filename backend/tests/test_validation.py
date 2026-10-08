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


@pytest.mark.asyncio
async def test_validation_decimal_precision_floating_boundary(db_session: AsyncSession):
    """
    Ensure 0.1 + 0.2 == 0.3 without binary floating-point drift (0.30000000000000004).
    """
    engine = ValidationEngine(db_session)
    extraction = InvoiceExtractionSchema(
        invoice_number="INV-DECIMAL-PRECISION",
        invoice_date="2026-10-01",
        vendor_name="Acme Industrial Supplies",
        currency="USD",
        subtotal=0.10,
        tax=0.20,
        total=0.30,
        po_number=None,
    )
    confidences = {k: 0.99 for k in ["invoice_number", "total", "subtotal", "tax"]}
    result = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=extraction,
        field_confidences=confidences,
    )
    math_finding = next(f for f in result.findings if f.rule_name == "tax_subtotal_arithmetic")
    assert math_finding.passed is True


@pytest.mark.asyncio
async def test_validation_po_tolerance_strict_and_boundaries(db_session: AsyncSession):
    """
    Test exact boundaries for strict AND tolerance rule:
    within_tolerance = (variance_pct <= 2.0%) AND (variance_abs <= $5.00).
    """
    from app.models.erp import PurchaseOrder

    # Create test POs
    po_250 = PurchaseOrder(
        id="po_bnd_250",
        tenant_id="tenant_test",
        po_number="PO-BND-250",
        vendor_id="vnd_acme",
        vendor_name="Acme Industrial Supplies",
        total_amount=250.00,
        currency="USD",
        status="OPEN",
    )
    po_100 = PurchaseOrder(
        id="po_bnd_100",
        tenant_id="tenant_test",
        po_number="PO-BND-100",
        vendor_id="vnd_acme",
        vendor_name="Acme Industrial Supplies",
        total_amount=100.00,
        currency="USD",
        status="OPEN",
    )
    po_1000 = PurchaseOrder(
        id="po_bnd_1000",
        tenant_id="tenant_test",
        po_number="PO-BND-1000",
        vendor_id="vnd_acme",
        vendor_name="Acme Industrial Supplies",
        total_amount=1000.00,
        currency="USD",
        status="OPEN",
    )
    db_session.add_all([po_250, po_100, po_1000])
    await db_session.commit()

    engine = ValidationEngine(db_session)
    confidences = {"invoice_number": 0.99, "total": 0.99, "po_number": 0.99}

    # Case A: Exactly 2.00% AND exactly $5.00 ($250 PO -> $255 invoice) -> PASS
    res_exact = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=InvoiceExtractionSchema(
            invoice_number="INV-BND-EXACT",
            invoice_date="2026-10-01",
            vendor_name="Acme",
            currency="USD",
            subtotal=231.82,
            tax=23.18,
            total=255.00,
            po_number="PO-BND-250",
        ),
        field_confidences=confidences,
    )
    assert any(f.rule_name == "po_tolerance_check" and f.passed for f in res_exact.findings)

    # Case B: Variance $2.01 (<= $5), but 2.01% (> 2.00%) ($100 PO -> $102.01 invoice) -> FAIL
    res_pct_fail = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=InvoiceExtractionSchema(
            invoice_number="INV-BND-PCT-FAIL",
            invoice_date="2026-10-01",
            vendor_name="Acme",
            currency="USD",
            subtotal=92.74,
            tax=9.27,
            total=102.01,
            po_number="PO-BND-100",
        ),
        field_confidences=confidences,
    )
    assert any(f.rule_name == "po_tolerance_check" and not f.passed for f in res_pct_fail.findings)

    # Case C: Variance 0.501% (<= 2.00%), but $5.01 (> $5.00) ($1000 PO -> $1005.01 invoice) -> FAIL
    res_abs_fail = await engine.validate_invoice(
        tenant_id="tenant_test",
        extraction=InvoiceExtractionSchema(
            invoice_number="INV-BND-ABS-FAIL",
            invoice_date="2026-10-01",
            vendor_name="Acme",
            currency="USD",
            subtotal=913.65,
            tax=91.36,
            total=1005.01,
            po_number="PO-BND-1000",
        ),
        field_confidences=confidences,
    )
    assert any(f.rule_name == "po_tolerance_check" and not f.passed for f in res_abs_fail.findings)

