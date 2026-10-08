import pytest
from datetime import timedelta
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.document import Document
from app.models.review import ReviewTask
from app.models.user import User

settings = get_settings()


@pytest.mark.asyncio
async def test_security_matrix_role_boundaries(
    client: AsyncClient,
    admin_token: str,
    ops_token: str,
    reviewer_token: str,
    viewer_token: str,
    db_session: AsyncSession,
):
    """
    Test RBAC authorization boundaries across all 4 roles:
    - Admin: Full capabilities including system config and document deletion
    - Ops Manager: Ingestion, review approvals, knowledge, but no document deletion or system config
    - Reviewer: Inspection, human review approvals/edits, knowledge search, but no document create/delete/reprocess
    - Viewer: Strictly read-only; mutations are denied
    """
    # 1. Document Deletion: ONLY Admin permitted
    doc = Document(
        id="doc_sec_test",
        tenant_id="tenant_test",
        filename="test.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/path.pdf",
        status="QUEUED",
    )
    db_session.add(doc)
    await db_session.commit()

    # Viewer cannot delete -> 403
    res_viewer_del = await client.delete(
        f"/api/v1/documents/{doc.id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert res_viewer_del.status_code == 403

    # Reviewer cannot delete -> 403
    res_rev_del = await client.delete(
        f"/api/v1/documents/{doc.id}",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert res_rev_del.status_code == 403

    # Ops Manager cannot delete -> 403
    res_ops_del = await client.delete(
        f"/api/v1/documents/{doc.id}",
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert res_ops_del.status_code == 403

    # 2. System Config / Provisioning: ONLY Admin permitted
    res_ops_cfg = await client.post(
        "/api/v1/auth/admin/users",
        headers={"Authorization": f"Bearer {ops_token}"},
        json={"email": "ops_test@test.com", "password": "pass", "full_name": "Test", "role": "viewer"},
    )
    assert res_ops_cfg.status_code == 403

    res_rev_cfg = await client.post(
        "/api/v1/auth/admin/users",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={"email": "rev_test@test.com", "password": "pass", "full_name": "Test", "role": "viewer"},
    )
    assert res_rev_cfg.status_code == 403

    # 3. Knowledge Indexing: Admin and Ops Manager allowed, Reviewer and Viewer denied
    res_rev_idx = await client.post(
        "/api/v1/knowledge/index",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={"title": "Test SOP", "content": "Sample content", "doc_type": "policy", "department": "finance"},
    )
    assert res_rev_idx.status_code == 403

    res_viewer_idx = await client.post(
        "/api/v1/knowledge/index",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"title": "Test SOP", "content": "Sample content", "doc_type": "policy", "department": "finance"},
    )
    assert res_viewer_idx.status_code == 403

    # Ops Manager can index knowledge
    res_ops_idx = await client.post(
        "/api/v1/knowledge/index",
        headers={"Authorization": f"Bearer {ops_token}"},
        json={"title": "Ops SOP", "content": "Approved standard SOP content for finance", "doc_type": "policy", "department": "operations"},
    )
    assert res_ops_idx.status_code == 201

    # 4. Review Decisions: Viewer denied
    task = ReviewTask(
        id="task_sec_test",
        tenant_id="tenant_test",
        document_id=doc.id,
        reason="Variance check",
        status="PENDING",
    )
    db_session.add(task)
    await db_session.commit()

    res_viewer_appr = await client.post(
        f"/api/v1/reviews/{task.id}/approve",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"action": "APPROVE", "comments": "Viewer attempting approval"},
    )
    assert res_viewer_appr.status_code == 403

    # Reviewer can view reviews
    res_rev_list = await client.get(
        "/api/v1/reviews",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert res_rev_list.status_code == 200

    # Admin can delete document
    res_admin_del = await client.delete(
        f"/api/v1/documents/{doc.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin_del.status_code == 204


@pytest.mark.asyncio
async def test_authentication_failure_modes(client: AsyncClient, db_session: AsyncSession):
    """
    Test authentication failure modes:
    - Missing Authorization header
    - Malformed token
    - Expired token
    - Wrong HMAC signing key
    - Missing tenant claim
    - Deactivated / inactive user
    """
    # 1. Missing Authorization header
    res_no_auth = await client.get("/api/v1/auth/me")
    assert res_no_auth.status_code == 401
    assert "Authorization header is missing" in res_no_auth.json()["error"]["message"]

    # 2. Malformed token
    res_malformed = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert res_malformed.status_code == 401

    # 3. Expired token
    expired_token = create_access_token(
        subject="usr_admin_1",
        tenant_id="tenant_test",
        role="admin",
        expires_delta=timedelta(seconds=-3600),  # expired 1 hour ago
    )
    res_expired = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401

    # 4. Wrong signing key
    fake_token = jwt.encode(
        {"sub": "usr_admin_1", "tenant_id": "tenant_test", "role": "admin"},
        "completely-wrong-signing-key-secret-12345",
        algorithm="HS256",
    )
    res_wrong_key = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert res_wrong_key.status_code == 401

    # 5. Missing tenant claim
    no_tenant_token = jwt.encode(
        {"sub": "usr_admin_1", "role": "admin"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    res_no_tenant = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {no_tenant_token}"},
    )
    assert res_no_tenant.status_code == 401

    # 6. Deactivated / Inactive user
    deactivated_user = User(
        id="usr_deactivated",
        tenant_id="tenant_test",
        email="inactive@test.com",
        hashed_password="somehash",
        full_name="Inactive User",
        role="reviewer",
        is_active=False,
    )
    db_session.add(deactivated_user)
    await db_session.commit()

    deact_token = create_access_token(
        subject="usr_deactivated",
        tenant_id="tenant_test",
        role="reviewer",
    )
    res_deact = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {deact_token}"},
    )
    assert res_deact.status_code == 401
    assert "deactivated" in res_deact.json()["error"]["message"].lower()
