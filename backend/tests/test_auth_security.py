import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_registration_role_escalation_blocked(client: AsyncClient):
    """
    Ensure anonymous users cannot self-register as admin or ops_manager.
    Pydantic Literal['viewer', 'reviewer'] rejects privileged roles with 422.
    """
    # Attempt to register as admin
    res_admin = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "hacker_admin@test.com",
            "password": "password123",
            "full_name": "Hacker Admin",
            "role": "admin",
            "tenant_slug": "test-corp",
        },
    )
    assert res_admin.status_code == 422

    # Attempt to register as ops_manager
    res_ops = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "hacker_ops@test.com",
            "password": "password123",
            "full_name": "Hacker Ops",
            "role": "ops_manager",
            "tenant_slug": "test-corp",
        },
    )
    assert res_ops.status_code == 422


@pytest.mark.asyncio
async def test_registration_allowed_roles(client: AsyncClient):
    """Ensure anonymous users can only self-register as reviewer or viewer."""
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "legit_reviewer@test.com",
            "password": "password123",
            "full_name": "Legit Reviewer",
            "role": "reviewer",
            "tenant_slug": "test-corp",
        },
    )
    assert res.status_code == 201
    assert res.json()["role"] == "reviewer"


@pytest.mark.asyncio
async def test_admin_user_provisioning_endpoint(
    client: AsyncClient,
    admin_token: str,
    reviewer_token: str,
):
    """
    Ensure only users with SYSTEM_CONFIG permission (admins) can call /auth/admin/users.
    Reviewer receives 403 Forbidden.
    """
    headers_reviewer = {"Authorization": f"Bearer {reviewer_token}"}
    headers_admin = {"Authorization": f"Bearer {admin_token}"}

    # Reviewer attempts to provision an ops_manager -> 403
    forbidden_res = await client.post(
        "/api/v1/auth/admin/users",
        headers=headers_reviewer,
        json={
            "email": "new_ops@test.com",
            "password": "password123",
            "full_name": "New Ops",
            "role": "ops_manager",
        },
    )
    assert forbidden_res.status_code == 403

    # Admin provisions ops_manager -> 201
    success_res = await client.post(
        "/api/v1/auth/admin/users",
        headers=headers_admin,
        json={
            "email": "new_ops_success@test.com",
            "password": "password123",
            "full_name": "New Ops Manager",
            "role": "ops_manager",
        },
    )
    assert success_res.status_code == 201
    assert success_res.json()["role"] == "ops_manager"


@pytest.mark.asyncio
async def test_dev_token_endpoint(client: AsyncClient):
    """Ensure dev-token route allows development role switching without passwords."""
    res = await client.post(
        "/api/v1/auth/dev-token",
        json={"role": "admin"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "admin"


def test_production_secret_key_validation():
    """Ensure Settings fails fast when ENVIRONMENT=production has weak or default SECRET_KEY."""
    from app.core.config import Settings
    from pydantic import ValidationError as PydanticValidationError

    # Default secret in production should fail
    with pytest.raises(PydanticValidationError) as exc_info:
        Settings(ENVIRONMENT="production")
    assert "Production environment requires a strong" in str(exc_info.value)

    # Valid production settings should succeed
    valid_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        SECRET_KEY="a-very-long-production-grade-secret-key-32chars!",
        DATABASE_URL="postgresql+asyncpg://prod_user:prod_pass@db:5432/opspilot",
        WORKER_MODE="redis",
        DEFAULT_LLM_PROVIDER="openai",
        OPENAI_API_KEY="sk-prod-test-key-12345",
        ENABLE_DEMO_SEED=False,
        USE_IN_MEMORY_QUEUE=False,
        STORAGE_TYPE="s3",
        CORS_ORIGINS=["https://app.opspilot.com"],
    )
    assert valid_settings.ENVIRONMENT == "production"
