import json
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.extraction import DocumentExtraction
from app.models.review import ReviewTask


@pytest.mark.asyncio
async def test_reviewer_cannot_approve_high_value_invoice(
    client: AsyncClient,
    reviewer_token: str,
    db_session: AsyncSession,
):
    """Reviewer cannot approve high-value (>= $10,000) invoices via /approve."""
    doc = Document(
        id="doc_hv_approve_test",
        tenant_id="tenant_test",
        filename="high_value.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/high_value.pdf",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)

    data = {
        "invoice_number": "INV-HV-999",
        "invoice_date": "2026-10-01",
        "vendor_name": "MegaCorp",
        "subtotal": 12000.00,
        "tax": 1200.00,
        "total": 13200.00,
        "currency": "USD",
    }
    ext = DocumentExtraction(
        id="ext_hv_approve_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        raw_json=json.dumps(data),
        structured_data=json.dumps(data),
        field_confidences=json.dumps({}),
        is_valid=True,
    )
    db_session.add(ext)

    task = ReviewTask(
        id="task_hv_approve_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="High-value threshold check",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {reviewer_token}"}
    res = await client.post(
        f"/api/v1/reviews/{task.id}/approve",
        headers=headers,
        json={"action": "APPROVE", "comments": "Attempting reviewer approval"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "AUTHORIZATION_FAILED"


@pytest.mark.asyncio
async def test_ops_manager_can_approve_high_value_invoice(
    client: AsyncClient,
    ops_token: str,
    db_session: AsyncSession,
):
    """Ops Manager can approve high-value invoices."""
    doc = Document(
        id="doc_hv_ops_test",
        tenant_id="tenant_test",
        filename="high_value_ops.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/high_value_ops.pdf",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)

    data = {
        "invoice_number": "INV-OPS-999",
        "invoice_date": "2026-10-01",
        "vendor_name": "MegaCorp",
        "subtotal": 10000.00,
        "tax": 1000.00,
        "total": 11000.00,
        "currency": "USD",
    }
    ext = DocumentExtraction(
        id="ext_hv_ops_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        raw_json=json.dumps(data),
        structured_data=json.dumps(data),
        field_confidences=json.dumps({}),
        is_valid=True,
    )
    db_session.add(ext)

    task = ReviewTask(
        id="task_hv_ops_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="High-value check",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {ops_token}"}
    res = await client.post(
        f"/api/v1/reviews/{task.id}/approve",
        headers=headers,
        json={"action": "APPROVE", "comments": "Approved by ops manager"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_admin_can_approve_high_value_invoice(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    """Admin can approve high-value invoices."""
    doc = Document(
        id="doc_hv_admin_test",
        tenant_id="tenant_test",
        filename="high_value_admin.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/high_value_admin.pdf",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)

    data = {
        "invoice_number": "INV-ADM-999",
        "invoice_date": "2026-10-01",
        "vendor_name": "MegaCorp",
        "subtotal": 20000.00,
        "tax": 2000.00,
        "total": 22000.00,
        "currency": "USD",
    }
    ext = DocumentExtraction(
        id="ext_hv_admin_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        raw_json=json.dumps(data),
        structured_data=json.dumps(data),
        field_confidences=json.dumps({}),
        is_valid=True,
    )
    db_session.add(ext)

    task = ReviewTask(
        id="task_hv_admin_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="High-value check",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.post(
        f"/api/v1/reviews/{task.id}/approve",
        headers=headers,
        json={"action": "APPROVE", "comments": "Approved by admin"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_resolved_task_cannot_be_approved_again(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    """A resolved review task cannot be transitioned to RESOLVED again."""
    doc = Document(
        id="doc_double_appr",
        tenant_id="tenant_test",
        filename="test.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/test.pdf",
        status="APPROVED",
    )
    db_session.add(doc)

    task = ReviewTask(
        id="task_already_resolved",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="Check",
        status="RESOLVED",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.post(
        f"/api/v1/reviews/{task.id}/approve",
        headers=headers,
        json={"action": "APPROVE"},
    )
    assert res.status_code in (400, 422)
    assert "VALIDATION_FAILED" in res.json()["error"]["code"]


@pytest.mark.asyncio
async def test_rejected_task_cannot_be_approved(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    """A rejected review task cannot be transitioned to RESOLVED."""
    doc = Document(
        id="doc_rejected_appr",
        tenant_id="tenant_test",
        filename="test.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/test.pdf",
        status="REJECTED",
    )
    db_session.add(doc)

    task = ReviewTask(
        id="task_already_rejected",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="Check",
        status="REJECTED",
    )
    db_session.add(task)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.post(
        f"/api/v1/reviews/{task.id}/approve",
        headers=headers,
        json={"action": "APPROVE"},
    )
    assert res.status_code in (400, 422)
    assert "VALIDATION_FAILED" in res.json()["error"]["code"]
