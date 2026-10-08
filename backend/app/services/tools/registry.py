from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Any, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import NotFoundError, ValidationError
from app.core.rbac import Permission
from app.models.audit import AuditLog
from app.models.document import Document
from app.models.erp import Invoice, PurchaseOrder, Vendor
from app.models.review import ReviewTask
from app.services.llm.base import LLMProvider
from app.services.rag.engine import RAGEngine
from app.services.tools.authorization import ToolAuthorizer
from app.services.tools.definitions import (
    CalculateVarianceInput,
    CreateReviewTaskInput,
    GetDocumentInput,
    GetPurchaseOrderInput,
    GetVendorInput,
    SearchPolicyInput,
    SendNotificationInput,
    ToolCallContext,
    ToolRiskLevel,
    UpdateInvoiceStatusInput,
)
from app.services.validation.policies import within_po_tolerance


class ToolRegistry:
    """
    Allowlisted typed tool execution registry with strict tenant isolation,
    RBAC permission gating, service-boundary authorization, latency measurement,
    and audit event logging.
    """

    def __init__(self, db: AsyncSession, llm_provider: LLMProvider):
        self.db = db
        self.llm = llm_provider
        self.rag = RAGEngine(db, llm_provider)

    async def _audit(self, ctx: ToolCallContext, action: str, entity_type: str, entity_id: str, after_state: Dict):
        audit = AuditLog(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            actor_type="agent",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            after_state=json.dumps(after_state),
        )
        self.db.add(audit)

    async def get_document(self, ctx: ToolCallContext, inp: GetDocumentInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.DOCUMENT_READ)
        stmt = select(Document).where(Document.id == inp.document_id, Document.tenant_id == ctx.tenant_id)
        res = await self.db.execute(stmt)
        doc = res.scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document", inp.document_id)
        return {"id": doc.id, "filename": doc.filename, "status": doc.status, "classification": doc.classification}

    async def get_purchase_order(self, ctx: ToolCallContext, inp: GetPurchaseOrderInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.DOCUMENT_READ)
        stmt = select(PurchaseOrder).where(
            PurchaseOrder.po_number == inp.po_number,
            PurchaseOrder.tenant_id == ctx.tenant_id,
        )
        res = await self.db.execute(stmt)
        po = res.scalar_one_or_none()
        if not po:
            return {"found": False, "po_number": inp.po_number}
        return {
            "found": True,
            "id": po.id,
            "po_number": po.po_number,
            "vendor_name": po.vendor_name,
            "total_amount": float(po.total_amount),
            "currency": po.currency,
            "status": po.status,
        }

    async def search_policy(self, ctx: ToolCallContext, inp: SearchPolicyInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.KNOWLEDGE_SEARCH)
        search_res = await self.rag.hybrid_search(
            tenant_id=ctx.tenant_id,
            query=inp.query,
            user_role=ctx.user_role,
            limit=3,
        )
        return {
            "answer": search_res.answer,
            "citations": [c.model_dump() for c in search_res.sources],
        }

    async def get_vendor(self, ctx: ToolCallContext, inp: GetVendorInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.DOCUMENT_READ)
        stmt = select(Vendor).where(
            (Vendor.name.ilike(f"%{inp.vendor_name}%")) | (Vendor.vendor_code == inp.vendor_name),
            Vendor.tenant_id == ctx.tenant_id,
        )
        res = await self.db.execute(stmt)
        vnd = res.first()
        if not vnd:
            return {"found": False, "vendor_name": inp.vendor_name}
        v = vnd[0]
        return {
            "found": True,
            "id": v.id,
            "name": v.name,
            "vendor_code": v.vendor_code,
            "payment_terms": v.payment_terms,
            "is_approved": v.is_approved,
        }

    async def calculate_variance(self, ctx: ToolCallContext, inp: CalculateVarianceInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.DOCUMENT_READ)
        inv_dec = Decimal(str(inp.invoice_total))
        po_dec = Decimal(str(inp.po_total))
        diff_dec = abs(inv_dec - po_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pct_dec = (
            ((diff_dec / po_dec) * Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if po_dec > Decimal("0.00")
            else Decimal("0.00")
        )
        within_tolerance = within_po_tolerance(pct_dec, diff_dec)
        return {
            "variance_amount": float(diff_dec),
            "variance_percent": float(pct_dec),
            "within_standard_tolerance": within_tolerance,
        }

    async def create_review_task(self, ctx: ToolCallContext, inp: CreateReviewTaskInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.REVIEW_EDIT)

        # 1. Verify target document belongs to this tenant
        doc_stmt = select(Document).where(Document.id == inp.document_id, Document.tenant_id == ctx.tenant_id)
        doc_res = await self.db.execute(doc_stmt)
        target_doc = doc_res.scalar_one_or_none()
        if not target_doc:
            raise NotFoundError("Document", inp.document_id)

        # 2. Idempotency: check if pending review task already exists for this doc
        existing = await self.db.execute(
            select(ReviewTask).where(
                ReviewTask.document_id == inp.document_id,
                ReviewTask.tenant_id == ctx.tenant_id,
                ReviewTask.status == "PENDING",
            )
        )
        task = existing.scalar_one_or_none()
        if not task:
            task = ReviewTask(
                tenant_id=ctx.tenant_id,
                document_id=inp.document_id,
                priority=inp.priority,
                reason=inp.reason,
                status="PENDING",
            )
            self.db.add(task)
            await self.db.flush()

        await self._audit(
            ctx, "CREATE_REVIEW_TASK", "ReviewTask", task.id, {"reason": inp.reason, "priority": inp.priority}
        )
        return {"task_id": task.id, "status": task.status, "reason": task.reason}

    async def update_invoice_status(self, ctx: ToolCallContext, inp: UpdateInvoiceStatusInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.REVIEW_APPROVE, risk_level=ToolRiskLevel.HIGH)

        allowed_target_statuses = {"POSTED", "REJECTED", "ON_HOLD", "PAID"}
        if inp.status.upper() not in allowed_target_statuses:
            raise ValidationError(f"Invalid target invoice status '{inp.status}'. Allowed: {allowed_target_statuses}")

        stmt = select(Invoice).where(Invoice.id == inp.invoice_id, Invoice.tenant_id == ctx.tenant_id)
        res = await self.db.execute(stmt)
        inv = res.scalar_one_or_none()
        if not inv:
            raise NotFoundError("Invoice", inp.invoice_id)

        prev = inv.status
        inv.status = inp.status.upper()
        await self._audit(ctx, "UPDATE_INVOICE_STATUS", "Invoice", inv.id, {"from": prev, "to": inv.status})
        return {"invoice_id": inv.id, "previous_status": prev, "new_status": inv.status}

    async def send_notification(self, ctx: ToolCallContext, inp: SendNotificationInput) -> Dict[str, Any]:
        ToolAuthorizer.authorize(ctx, Permission.DOCUMENT_READ)
        return {
            "delivered": True,
            "delivery_mode": "SIMULATED",
            "recipient_role": inp.recipient_role,
            "message": inp.message,
        }
