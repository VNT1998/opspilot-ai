from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
import app.db.session as session_module
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.erp import PurchaseOrder, PurchaseOrderLine, Vendor
from app.models.tenant import Tenant
from app.models.user import User

test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Bind worker's sessionmaker to the test session maker
session_module.AsyncSessionLocal = TestAsyncSessionLocal
session_module.engine = test_engine


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestAsyncSessionLocal() as session:
        # Seed test tenant and users
        tenant = Tenant(
            id="tenant_test",
            name="Test Corp",
            slug="test-corp",
            plan="enterprise",
        )
        session.add(tenant)
        await session.flush()

        users = [
            User(
                id="usr_admin_1",
                tenant_id=tenant.id,
                email="admin@test.com",
                hashed_password=hash_password("admin123"),
                full_name="Admin Test",
                role="admin",
                is_active=True,
            ),
            User(
                id="usr_ops_1",
                tenant_id=tenant.id,
                email="ops@test.com",
                hashed_password=hash_password("ops123"),
                full_name="Ops Manager Test",
                role="ops_manager",
                is_active=True,
            ),
            User(
                id="usr_reviewer_1",
                tenant_id=tenant.id,
                email="reviewer@test.com",
                hashed_password=hash_password("reviewer123"),
                full_name="Reviewer Test",
                role="reviewer",
                is_active=True,
            ),
            User(
                id="usr_viewer_1",
                tenant_id=tenant.id,
                email="viewer@test.com",
                hashed_password=hash_password("viewer123"),
                full_name="Viewer Test",
                role="viewer",
                is_active=True,
            ),
        ]
        session.add_all(users)

        # Seed sample Vendor and PO
        vendor = Vendor(
            id="vnd_test_1",
            tenant_id=tenant.id,
            name="Acme Industrial Supplies",
            vendor_code="ACME-001",
            payment_terms="Net 30",
            is_approved=True,
        )
        session.add(vendor)
        await session.flush()

        po = PurchaseOrder(
            id="po_test_1",
            tenant_id=tenant.id,
            po_number="PO-9001",
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            total_amount=1450.00,
            currency="USD",
            status="OPEN",
        )
        po.lines.append(
            PurchaseOrderLine(
                tenant_id=tenant.id,
                line_number=1,
                description="Standard Enterprise Service License",
                quantity=1.0,
                unit_price=1318.18,
                total_price=1318.18,
            )
        )
        session.add(po)

        await session.commit()
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def admin_token() -> str:
    return create_access_token(
        subject="usr_admin_1",
        tenant_id="tenant_test",
        role="admin",
        extra_claims={"email": "admin@test.com", "name": "Admin Test"},
    )


@pytest.fixture
def ops_token() -> str:
    return create_access_token(
        subject="usr_ops_1",
        tenant_id="tenant_test",
        role="ops_manager",
        extra_claims={"email": "ops@test.com", "name": "Ops Manager Test"},
    )


@pytest.fixture
def reviewer_token() -> str:
    return create_access_token(
        subject="usr_reviewer_1",
        tenant_id="tenant_test",
        role="reviewer",
        extra_claims={"email": "reviewer@test.com", "name": "Reviewer Test"},
    )


@pytest.fixture
def viewer_token() -> str:
    return create_access_token(
        subject="usr_viewer_1",
        tenant_id="tenant_test",
        role="viewer",
        extra_claims={"email": "viewer@test.com", "name": "Viewer Test"},
    )
