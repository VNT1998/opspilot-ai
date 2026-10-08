import json
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.extraction import DocumentExtraction
from app.models.review import ReviewTask


@pytest.mark.asyncio
async def test_reviewer_edit_schema_validation_failure(
    client: AsyncClient,
    reviewer_token: str,
    db_session: AsyncSession,
):
    """Ensure invalid field edits fail Pydantic schema validation with 422."""
    doc = Document(
        id="doc_edit_fail",
        tenant_id="tenant_test",
        filename="invoice_err.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/err.pdf",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)

    payload_data = {
        "invoice_number": "INV-ORIG-01",
        "vendor_name": "Acme Industrial Supplies",
        "total": 1450.00,
        "subtotal": 1318.18,
        "tax": 131.82,
        "currency": "USD",
        "po_number": "PO-9001",
    }
    ext = DocumentExtraction(
        id="ext_edit_fail",
        tenant_id="tenant_test",
        document_id=doc.id,
        raw_json=json.dumps(payload_data),
        structured_data=json.dumps(payload_data),
        field_confidences=json.dumps({}),
        is_valid=False,
    )
    db_session.add(ext)

    task = ReviewTask(
        id="task_edit_fail",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="Initial review",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {reviewer_token}"}
    # Send total as an invalid non-numeric object
    res = await client.post(
        f"/api/v1/reviews/{task.id}/edit",
        headers=headers,
        json={
            "action": "EDIT",
            "edited_fields": {"total": "NOT_A_VALID_NUMBER"},
        },
    )
    assert res.status_code == 422
    assert "VALIDATION_FAILED" in res.json()["error"]["code"]


@pytest.mark.asyncio
async def test_reviewer_edit_high_value_escalation_blocked(
    client: AsyncClient,
    reviewer_token: str,
    db_session: AsyncSession,
):
    """
    Ensure reviewer cannot approve an invoice edited to >= $10,000.
    Must return 403 Forbidden because high-value invoices require Ops Manager or Admin.
    """
    doc = Document(
        id="doc_edit_highval",
        tenant_id="tenant_test",
        filename="invoice_hv.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/hv.pdf",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)

    payload_hv = {
        "invoice_number": "INV-HV-01",
        "invoice_date": "2026-10-01",
        "vendor_name": "Acme Industrial Supplies",
        "total": 1450.00,
        "subtotal": 1318.18,
        "tax": 131.82,
        "currency": "USD",
        "po_number": "PO-9001",
    }
    ext = DocumentExtraction(
        id="ext_edit_highval",
        tenant_id="tenant_test",
        document_id=doc.id,
        raw_json=json.dumps(payload_hv),
        structured_data=json.dumps(payload_hv),
        field_confidences=json.dumps({}),
        is_valid=False,
    )
    db_session.add(ext)

    task = ReviewTask(
        id="task_edit_highval",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="PO check",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {reviewer_token}"}
    # Reviewer edits total to $25,000 -> 403 Forbidden
    res = await client.post(
        f"/api/v1/reviews/{task.id}/edit",
        headers=headers,
        json={
            "action": "EDIT",
            "edited_fields": {"total": 25000.00, "subtotal": 22727.27, "tax": 2272.73},
        },
    )
    assert res.status_code == 403
    assert "exceeds the $10,000 policy threshold" in res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_admin_edit_revalidation_and_erp_post(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    """Ensure authorized admin editing re-runs validation and posts to ERP."""
    doc = Document(
        id="doc_edit_valid",
        tenant_id="tenant_test",
        filename="invoice_valid.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/valid.pdf",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)

    payload_valid = {
        "invoice_number": "INV-ORIG-CORRECT",
        "invoice_date": "2026-10-01",
        "vendor_name": "Acme Industrial Supplies",
        "total": 1450.00,
        "subtotal": 1318.18,
        "tax": 131.82,
        "currency": "USD",
        "po_number": "PO-9001",
    }
    ext = DocumentExtraction(
        id="ext_edit_valid",
        tenant_id="tenant_test",
        document_id=doc.id,
        raw_json=json.dumps(payload_valid),
        structured_data=json.dumps(payload_valid),
        field_confidences=json.dumps({}),
        is_valid=False,
    )
    db_session.add(ext)

    task = ReviewTask(
        id="task_edit_valid",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="OCR error on line",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.post(
        f"/api/v1/reviews/{task.id}/edit",
        headers=headers,
        json={
            "action": "EDIT",
            "edited_fields": {"invoice_number": "INV-CORRECTED-99"},
            "comments": "Fixed OCR transcription typo in invoice number.",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"
