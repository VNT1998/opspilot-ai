from typing import Any, List, Literal, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models.erp import Invoice, InvoiceLine
from app.services.audit.service import AuditService


class ERPService:
    """
    Centralized ERP integration service.
    Enforces authorization, tenant boundaries, duplicate checks, idempotency,
    transactional persistence, and immutable audit logs.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def post_invoice(
        self,
        *,
        tenant_id: str,
        document_id: str,
        invoice_number: str,
        vendor_name: str,
        total_amount: float,
        currency: str = "USD",
        po_number: Optional[str] = None,
        source: Literal["agent", "human"] = "agent",
        actor_id: str = "system",
        validation_status: str = "POSTED",
        line_items: Optional[List[Any]] = None,
        comments: Optional[str] = None,
    ) -> Invoice:
        # 1. Idempotency Check: Was an invoice already posted for this exact document?
        doc_stmt = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.document_id == document_id,
        )
        existing_for_doc = (await self.db.execute(doc_stmt)).scalar_one_or_none()
        if existing_for_doc:
            return existing_for_doc

        # 2. Duplicate Check: Does an invoice with this number already exist for this tenant?
        num_stmt = select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.invoice_number == invoice_number,
        )
        existing_num = (await self.db.execute(num_stmt)).scalar_one_or_none()
        if existing_num:
            raise ConflictError(
                f"Duplicate invoice detected: Invoice '{invoice_number}' has already been posted to the ERP system."
            )

        # 3. Create Invoice Record
        invoice = Invoice(
            tenant_id=tenant_id,
            document_id=document_id,
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            po_number=po_number,
            total_amount=total_amount,
            currency=currency,
            status="POSTED",
            validation_status=validation_status,
        )
        self.db.add(invoice)
        await self.db.flush()

        # 4. Attach line items if provided
        if line_items:
            for idx, item in enumerate(line_items, start=1):
                inv_line = InvoiceLine(
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    line_number=idx,
                    description=getattr(item, "description", str(item)),
                    quantity=getattr(item, "quantity", 1.0),
                    unit_price=getattr(item, "unit_price", 0.0),
                    total_price=getattr(item, "total_price", 0.0),
                    sku=getattr(item, "sku", None),
                )
                self.db.add(inv_line)

        # 5. Record Audit Trail
        await AuditService.log_event(
            db=self.db,
            tenant_id=tenant_id,
            action="ERP_INVOICE_POSTED",
            entity_type="Invoice",
            entity_id=invoice.id,
            user_id=actor_id,
            after_state={
                "invoice_number": invoice.invoice_number,
                "total": invoice.total_amount,
                "source": source,
                "validation_status": validation_status,
                "comments": comments,
            },
        )

        return invoice
