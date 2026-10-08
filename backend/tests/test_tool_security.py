import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError, NotFoundError
from app.models.document import Document
from app.models.erp import PurchaseOrder
from app.services.llm.mock_provider import MockLLMProvider
from app.services.tools.definitions import (
    CreateReviewTaskInput,
    GetDocumentInput,
    GetPurchaseOrderInput,
    ToolCallContext,
    UpdateInvoiceStatusInput,
)
from app.services.tools.registry import ToolRegistry


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def registry(db_session: AsyncSession, mock_llm):
    return ToolRegistry(db=db_session, llm_provider=mock_llm)


@pytest.mark.asyncio
async def test_tool_caller_tenant_isolation(
    registry: ToolRegistry,
    db_session: AsyncSession,
):
    """Tool caller cannot read documents owned by another tenant."""
    # Seed document under tenant_victim
    doc = Document(
        id="doc_victim_123",
        tenant_id="tenant_victim",
        filename="confidential.pdf",
        file_type="pdf",
        file_size=500,
        mime_type="application/pdf",
        storage_path="mock/confidential.pdf",
        status="PROCESSED",
    )
    db_session.add(doc)
    await db_session.commit()

    # Caller belongs to tenant_attacker
    attacker_ctx = ToolCallContext(
        tenant_id="tenant_attacker",
        user_id="usr_attacker",
        user_role="admin",
    )

    with pytest.raises(NotFoundError, match="Document"):
        await registry.get_document(attacker_ctx, GetDocumentInput(document_id="doc_victim_123"))


@pytest.mark.asyncio
async def test_tool_po_cross_tenant_isolation(
    registry: ToolRegistry,
    db_session: AsyncSession,
):
    """Tool caller cannot see POs from other tenants."""
    po = PurchaseOrder(
        id="po_victim_123",
        tenant_id="tenant_victim",
        po_number="PO-CONFIDENTIAL-99",
        vendor_id="vnd_test_1",
        vendor_name="Victim Vendor",
        total_amount=5000.0,
        currency="USD",
        status="OPEN",
    )
    db_session.add(po)
    await db_session.commit()

    attacker_ctx = ToolCallContext(
        tenant_id="tenant_attacker",
        user_id="usr_attacker",
        user_role="admin",
    )

    res = await registry.get_purchase_order(attacker_ctx, GetPurchaseOrderInput(po_number="PO-CONFIDENTIAL-99"))
    assert res["found"] is False


@pytest.mark.asyncio
async def test_tool_permission_escalation_blocked(
    registry: ToolRegistry,
):
    """Viewer role cannot execute high-risk update_invoice_status."""
    viewer_ctx = ToolCallContext(
        tenant_id="tenant_test",
        user_id="usr_viewer",
        user_role="viewer",
    )

    with pytest.raises(AuthorizationError):
        await registry.update_invoice_status(
            viewer_ctx,
            UpdateInvoiceStatusInput(invoice_id="inv_1", status="POSTED"),
        )


@pytest.mark.asyncio
async def test_tool_missing_context_rejected(
    registry: ToolRegistry,
):
    """Empty tenant or user ID must be rejected by service boundary."""
    invalid_ctx = ToolCallContext(
        tenant_id="",
        user_id="",
        user_role="admin",
    )

    with pytest.raises(AuthorizationError):
        await registry.get_purchase_order(invalid_ctx, GetPurchaseOrderInput(po_number="PO-123"))


@pytest.mark.asyncio
async def test_create_review_task_cross_tenant_rejected(
    registry: ToolRegistry,
    db_session: AsyncSession,
):
    """Creating review task for another tenant's document is rejected."""
    doc = Document(
        id="doc_victim_task",
        tenant_id="tenant_victim",
        filename="victim.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/victim.pdf",
        status="PROCESSED",
    )
    db_session.add(doc)
    await db_session.commit()

    attacker_ctx = ToolCallContext(
        tenant_id="tenant_attacker",
        user_id="usr_attacker",
        user_role="reviewer",
    )

    with pytest.raises(NotFoundError):
        await registry.create_review_task(
            attacker_ctx,
            CreateReviewTaskInput(document_id="doc_victim_task", reason="Malicious escalation"),
        )
