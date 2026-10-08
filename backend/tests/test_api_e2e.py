import io
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_e2e_document_upload_and_lifecycle(
    client: AsyncClient,
    admin_token: str,
    reviewer_token: str,
):
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    headers_reviewer = {"Authorization": f"Bearer {reviewer_token}"}

    # 1. Upload document (multipart file)
    file_content = b"Invoice: INV-E2E-100\nVendor: Acme Industrial Supplies\nTotal: $1450.00\nPO: PO-9001"
    files = {"file": ("invoice_sample.txt", io.BytesIO(file_content), "text/plain")}

    upload_res = await client.post("/api/v1/documents", headers=headers_admin, files=files)
    assert upload_res.status_code == 202
    upload_data = upload_res.json()
    doc_id = upload_data["id"]
    assert upload_data["status"] == "QUEUED"

    # 2. List documents
    list_res = await client.get("/api/v1/documents", headers=headers_admin)
    assert list_res.status_code == 200
    docs = list_res.json()["items"]
    assert any(d["id"] == doc_id for d in docs)

    # 3. Get document details
    get_res = await client.get(f"/api/v1/documents/{doc_id}", headers=headers_admin)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == doc_id

    # 4. Create and Approve Review Task
    import app.db.session as session_module
    from app.models.review import ReviewTask

    async with session_module.AsyncSessionLocal() as db:
        review_task = ReviewTask(
            tenant_id="tenant_test",
            document_id=doc_id,
            reason="Sample review test",
            status="PENDING",
            priority="MEDIUM",
        )
        db.add(review_task)
        await db.commit()
        await db.refresh(review_task)
        task_id = review_task.id

    # Reviewer approves task
    approve_res = await client.post(
        f"/api/v1/reviews/{task_id}/approve",
        headers=headers_reviewer,
        json={"action": "APPROVE", "comments": "Approved following invoice validation."},
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "RESOLVED"

    # 5. Check Audit Logs
    audit_res = await client.get("/api/v1/audit-logs", headers=headers_admin)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert any(log_item["entity_id"] == task_id for log_item in logs)

    # 6. Check Operational Metrics
    metrics_res = await client.get("/api/v1/metrics", headers=headers_admin)
    assert metrics_res.status_code == 200
    metrics_data = metrics_res.json()
    assert metrics_data["total_documents"] >= 1
