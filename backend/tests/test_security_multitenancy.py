import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.document import Document
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.review import ReviewTask
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit.service import AuditService


@pytest.fixture
async def setup_tenants_and_users(db_session: AsyncSession):
    """Sets up Tenant Alpha (tenant_test from conftest) and a distinct Tenant Beta."""
    tenant_beta = Tenant(
        id="tenant_beta",
        name="Beta Logistics Corp",
        slug="beta-logistics",
        plan="enterprise",
    )
    db_session.add(tenant_beta)

    user_beta_admin = User(
        id="usr_beta_admin",
        tenant_id="tenant_beta",
        email="admin@beta-logistics.com",
        hashed_password=hash_password("betaadmin123"),
        full_name="Beta Admin",
        role="admin",
        is_active=True,
    )
    user_beta_reviewer = User(
        id="usr_beta_reviewer",
        tenant_id="tenant_beta",
        email="reviewer@beta-logistics.com",
        hashed_password=hash_password("betareviewer123"),
        full_name="Beta Reviewer",
        role="reviewer",
        is_active=True,
    )
    db_session.add_all([user_beta_admin, user_beta_reviewer])
    await db_session.commit()

    token_beta_admin = create_access_token(
        subject="usr_beta_admin",
        tenant_id="tenant_beta",
        role="admin",
        extra_claims={"email": "admin@beta-logistics.com", "name": "Beta Admin"},
    )
    token_beta_reviewer = create_access_token(
        subject="usr_beta_reviewer",
        tenant_id="tenant_beta",
        role="reviewer",
        extra_claims={"email": "reviewer@beta-logistics.com", "name": "Beta Reviewer"},
    )

    return {
        "tenant_beta": tenant_beta,
        "token_beta_admin": token_beta_admin,
        "token_beta_reviewer": token_beta_reviewer,
    }


@pytest.mark.asyncio
async def test_cross_tenant_document_read_denied(
    client: AsyncClient,
    admin_token: str,
    setup_tenants_and_users,
):
    """
    Ensure Tenant Beta user cannot view or retrieve documents owned by Tenant Alpha.
    Returns 404 (resource does not exist within the requester's tenant boundary).
    """
    headers_alpha = {"Authorization": f"Bearer {admin_token}"}
    headers_beta = {"Authorization": f"Bearer {setup_tenants_and_users['token_beta_admin']}"}

    # Tenant Alpha uploads a document
    file_content = b"Confidential Alpha Financial Statement 2026"
    files = {"file": ("alpha_secret.txt", io.BytesIO(file_content), "text/plain")}
    upload_res = await client.post("/api/v1/documents", headers=headers_alpha, files=files)
    assert upload_res.status_code == 202
    doc_alpha_id = upload_res.json()["id"]

    # Tenant Alpha can access it
    alpha_get = await client.get(f"/api/v1/documents/{doc_alpha_id}", headers=headers_alpha)
    assert alpha_get.status_code == 200

    # Tenant Beta attempts to access Tenant Alpha's document
    beta_get = await client.get(f"/api/v1/documents/{doc_alpha_id}", headers=headers_beta)
    assert beta_get.status_code == 404
    assert beta_get.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_cross_tenant_document_listing_isolation(
    client: AsyncClient,
    admin_token: str,
    setup_tenants_and_users,
):
    """
    Ensure document list endpoint returns strictly the caller's tenant documents.
    """
    headers_alpha = {"Authorization": f"Bearer {admin_token}"}
    headers_beta = {"Authorization": f"Bearer {setup_tenants_and_users['token_beta_admin']}"}

    # Upload doc for Alpha
    file_alpha = b"Invoice INV-ALPHA-001 for Alpha Corp"
    upload_a = await client.post(
        "/api/v1/documents",
        headers=headers_alpha,
        files={"file": ("alpha_inv.txt", io.BytesIO(file_alpha), "text/plain")},
    )
    doc_a_id = upload_a.json()["id"]

    # Upload doc for Beta
    file_beta = b"Invoice INV-BETA-001 for Beta Logistics"
    upload_b = await client.post(
        "/api/v1/documents",
        headers=headers_beta,
        files={"file": ("beta_inv.txt", io.BytesIO(file_beta), "text/plain")},
    )
    doc_b_id = upload_b.json()["id"]

    # Query Alpha list
    list_a = await client.get("/api/v1/documents", headers=headers_alpha)
    assert list_a.status_code == 200
    items_a = [d["id"] for d in list_a.json()["items"]]
    assert doc_a_id in items_a
    assert doc_b_id not in items_a

    # Query Beta list
    list_b = await client.get("/api/v1/documents", headers=headers_beta)
    assert list_b.status_code == 200
    items_b = [d["id"] for d in list_b.json()["items"]]
    assert doc_b_id in items_b
    assert doc_a_id not in items_b


@pytest.mark.asyncio
async def test_cross_tenant_review_task_approval_denied(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    setup_tenants_and_users,
):
    """
    Ensure Tenant Beta reviewer cannot approve or modify Tenant Alpha review tasks.
    """
    headers_alpha = {"Authorization": f"Bearer {admin_token}"}
    headers_beta = {"Authorization": f"Bearer {setup_tenants_and_users['token_beta_reviewer']}"}

    # Create document and review task in Tenant Alpha
    doc = Document(
        tenant_id="tenant_test",
        filename="alpha_po_discrepancy.txt",
        file_type="txt",
        file_size=100,
        mime_type="text/plain",
        storage_path="mock/alpha.txt",
        status="REVIEW_REQUIRED",
    )
    db_session.add(doc)
    await db_session.flush()

    task_alpha = ReviewTask(
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="Variance in total amount vs PO-9001",
        status="PENDING",
        priority="HIGH",
    )
    db_session.add(task_alpha)
    await db_session.commit()

    # Tenant Beta reviewer attempts to approve Tenant Alpha's review task
    res = await client.post(
        f"/api/v1/reviews/{task_alpha.id}/approve",
        headers=headers_beta,
        json={"action": "APPROVE", "comments": "Malicious cross-tenant override attempt."},
    )
    assert res.status_code == 404

    # Verify task state in Alpha remains PENDING
    await db_session.refresh(task_alpha)
    assert task_alpha.status == "PENDING"


@pytest.mark.asyncio
async def test_cross_tenant_rag_retrieval_isolation(
    client: AsyncClient,
    admin_token: str,
    setup_tenants_and_users,
):
    """
    Ensure RAG hybrid search does not leak confidential policy chunks across tenants.
    """
    headers_alpha = {"Authorization": f"Bearer {admin_token}"}
    headers_beta = {"Authorization": f"Bearer {setup_tenants_and_users['token_beta_admin']}"}

    # Alpha indexes proprietary pricing & secret approval rules
    index_res = await client.post(
        "/api/v1/knowledge/index",
        headers=headers_alpha,
        json={
            "title": "Alpha Confidential Executive Bonus & Pricing SOP",
            "content": "Secret Project Starlight: Executive bonuses above $50,000 are pre-authorized for Q4.",
            "doc_type": "policy",
            "department": "executive",
            "acl_roles": ["admin", "reviewer"],
        },
    )
    assert index_res.status_code == 201

    # Alpha searches for it and retrieves it
    search_alpha = await client.post(
        "/api/v1/knowledge/search",
        headers=headers_alpha,
        json={"query": "Secret Project Starlight executive bonus authorization", "limit": 3},
    )
    assert search_alpha.status_code == 200
    alpha_sources = search_alpha.json()["sources"]
    assert len(alpha_sources) > 0
    assert any("Project Starlight" in s["snippet"] for s in alpha_sources)

    # Beta searches for the identical secret query - MUST return 0 Alpha sources
    search_beta = await client.post(
        "/api/v1/knowledge/search",
        headers=headers_beta,
        json={"query": "Secret Project Starlight executive bonus authorization", "limit": 3},
    )
    assert search_beta.status_code == 200
    beta_sources = search_beta.json()["sources"]
    assert len(beta_sources) == 0


@pytest.mark.asyncio
async def test_cross_tenant_audit_and_metrics_isolation(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
    setup_tenants_and_users,
):
    """
    Ensure audit logs and operational metrics queries are strictly isolated per tenant.
    """
    headers_alpha = {"Authorization": f"Bearer {admin_token}"}
    headers_beta = {"Authorization": f"Bearer {setup_tenants_and_users['token_beta_admin']}"}

    # Log an audit event for Alpha
    await AuditService.log_event(
        db=db_session,
        tenant_id="tenant_test",
        action="CONFIDENTIAL_ALPHA_AUDIT_ACTION",
        entity_type="SecurityTest",
        entity_id="sec-101",
        user_id="usr_admin_1",
        after_state={"secret": "alpha_only"},
    )
    await db_session.commit()

    # Query audit logs as Alpha
    audit_a = await client.get("/api/v1/audit-logs", headers=headers_alpha)
    assert audit_a.status_code == 200
    actions_a = [entry["action"] for entry in audit_a.json()]
    assert "CONFIDENTIAL_ALPHA_AUDIT_ACTION" in actions_a

    # Query audit logs as Beta - MUST NOT contain Alpha's audit event
    audit_b = await client.get("/api/v1/audit-logs", headers=headers_beta)
    assert audit_b.status_code == 200
    actions_b = [entry["action"] for entry in audit_b.json()]
    assert "CONFIDENTIAL_ALPHA_AUDIT_ACTION" not in actions_b

    # Verify metrics for Beta do not count Alpha resources
    metrics_b = await client.get("/api/v1/metrics", headers=headers_beta)
    assert metrics_b.status_code == 200
    assert metrics_b.json()["total_documents"] == 0
