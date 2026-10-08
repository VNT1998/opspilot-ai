import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import OpsPilotException
from app.core.logging import logger
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import *  # noqa: F401, F403 Ensure all models are registered
from app.services.queue.worker import get_job_worker

settings = get_settings()


async def seed_initial_demo_data():
    """Seeds default tenant, users, vendors, purchase orders, and corporate policies for testing."""
    from app.core.security import hash_password
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.erp import Vendor, PurchaseOrder, PurchaseOrderLine
    from app.services.rag.engine import RAGEngine
    from app.services.llm.factory import get_llm_provider
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Tenant).where(Tenant.slug == "nexus-corp"))
        if res.scalar_one_or_none():
            return  # Already seeded

        # 1. Create Default Tenant
        tenant = Tenant(
            id="tenant_nexus",
            name="Nexus Enterprise Solutions Inc.",
            slug="nexus-corp",
            plan="enterprise",
        )
        db.add(tenant)
        await db.flush()

        # 2. Create Users for all roles
        users = [
            User(
                id="usr_admin",
                tenant_id=tenant.id,
                email="admin@opspilot.ai",
                hashed_password=hash_password("admin123"),
                full_name="Alex Administrator",
                role="admin",
                is_active=True,
            ),
            User(
                id="usr_ops",
                tenant_id=tenant.id,
                email="ops@opspilot.ai",
                hashed_password=hash_password("ops123"),
                full_name="Morgan Ops Manager",
                role="ops_manager",
                is_active=True,
            ),
            User(
                id="usr_reviewer",
                tenant_id=tenant.id,
                email="reviewer@opspilot.ai",
                hashed_password=hash_password("reviewer123"),
                full_name="Sam Reviewer",
                role="reviewer",
                is_active=True,
            ),
            User(
                id="usr_viewer",
                tenant_id=tenant.id,
                email="viewer@opspilot.ai",
                hashed_password=hash_password("viewer123"),
                full_name="Taylor Viewer",
                role="viewer",
                is_active=True,
            ),
        ]
        db.add_all(users)

        # 3. Create Sample Vendors
        vendors = [
            Vendor(
                id="vnd_acme",
                tenant_id=tenant.id,
                name="Acme Industrial Supplies",
                vendor_code="ACME-001",
                contact_email="billing@acme.com",
                payment_terms="Net 30",
                is_approved=True,
            ),
            Vendor(
                id="vnd_globex",
                tenant_id=tenant.id,
                name="Globex Cloud Systems",
                vendor_code="GLB-500",
                contact_email="ar@globex.io",
                payment_terms="Net 15",
                is_approved=True,
            ),
        ]
        db.add_all(vendors)
        await db.flush()

        # 4. Create Active Purchase Orders
        po1 = PurchaseOrder(
            id="po_9001",
            tenant_id=tenant.id,
            po_number="PO-9001",
            vendor_id="vnd_acme",
            vendor_name="Acme Industrial Supplies",
            total_amount=1450.00,
            currency="USD",
            status="OPEN",
        )
        po1.lines.append(
            PurchaseOrderLine(
                tenant_id=tenant.id,
                line_number=1,
                description="Standard Enterprise Service License",
                quantity=1.0,
                unit_price=1318.18,
                total_price=1318.18,
                sku="SRV-100",
            )
        )
        db.add(po1)

        po2 = PurchaseOrder(
            id="po_9002",
            tenant_id=tenant.id,
            po_number="PO-9002",
            vendor_id="vnd_globex",
            vendor_name="Globex Cloud Systems",
            total_amount=4800.00,
            currency="USD",
            status="OPEN",
        )
        db.add(po2)
        await db.commit()

        # 5. Index Company Policy Document in RAG
        llm = get_llm_provider()
        rag = RAGEngine(db, llm)
        policy_content = """
--- Page 1 ---
Corporate Accounts Payable & Invoice Verification Policy (SOP-FIN-2026)

Section 1: Approval Matrix & Thresholds
1.1 Invoices below $5,000.00 matched to an approved Purchase Order within a 2.0% or $5.00 variance tolerance are eligible for automated straight-through processing (STP).
1.2 Invoices between $5,000.00 and $9,999.99 require automated matching and spot-check audit clearance.
1.3 Invoices exceeding $10,000.00 (High-Value Threshold) strictly require mandatory Operations Manager sign-off and two-party human review regardless of AI confidence scores.

--- Page 2 ---
Section 2: Three-Way Matching Rules
2.1 All vendor invoices must reference a valid and active Purchase Order (PO).
2.2 If the variance between the invoice total and the PO line item sum exceeds 2.0% or $5.00, the invoice must be routed to the Exception Review Queue.
2.3 Invoices with unverified vendor tax registration or missing vendor tax IDs must be held for compliance review.
2.4 Duplicate invoice numbers for the same supplier are categorically rejected to prevent duplicate disbursement.
        """
        await rag.index_document(
            tenant_id=tenant.id,
            title="AP Invoice Verification & Approval Policy (SOP-FIN-2026)",
            content=policy_content,
            doc_type="policy",
            department="finance",
            acl_roles=["admin", "ops_manager", "reviewer", "viewer"],
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed demo data
    try:
        await seed_initial_demo_data()
    except Exception as e:
        logger.warning(f"Seed data execution note: {e}")

    # Start async worker
    worker = get_job_worker()
    worker.start()

    yield

    # Shutdown: stop worker
    await worker.stop()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Agentic Document & Workflow Automation Platform with LangGraph, RAG, and Human-in-the-Loop review.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Correlation ID and Request Telemetry Middleware
@app.middleware("http")
async def telemetry_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:10]}"
    start_time = time.time()

    # Pass request_id to state
    request.state.request_id = request_id

    response = await call_next(request)

    latency_ms = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Processing-Time-MS"] = str(latency_ms)

    # Structured log
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({latency_ms}ms)",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )

    return response


# Centralized Exception Handler for OpsPilotException
@app.exception_handler(OpsPilotException)
async def opspilot_exception_handler(request: Request, exc: OpsPilotException):
    req_id = getattr(request.state, "request_id", "req_unknown")
    logger.warning(f"Application exception [{exc.code}]: {exc.message} (request_id={req_id})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": req_id,
                "retryable": exc.retryable,
                "details": exc.details,
            }
        },
    )


# Include API v1
app.include_router(api_v1_router)
