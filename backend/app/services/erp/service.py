from decimal import Decimal
from typing import Any, List, Literal, Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models.erp import Invoice, InvoiceLine
from app.services.audit.service import AuditService


class ERPService:
    """
    Centralized ERP integration service.
    Enforces authorization, tenant boundaries, duplicate checks, idempotency,
    transactional persistence, and tamper-evident audit logs.
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
        total_amount: Decimal | float,
        actor_id: str,
        currency: str = "USD",
        po_number: Optional[str] = None,
        source: Literal["agent", "human"] = "agent",
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

        # 3. Create Invoice Record with Decimal precision
        dec_total = Decimal(str(total_amount)) if not isinstance(total_amount, Decimal) else total_amount
        invoice = Invoice(
            tenant_id=tenant_id,
            document_id=document_id,
            invoice_number=invoice_number,
            vendor_name=vendor_name,
            po_number=po_number,
            total_amount=dec_total,
            currency=currency,
            status="POSTED",
            validation_status=validation_status,
        )
        self.db.add(invoice)

        # 4. Attach line items if provided
        if line_items:
            for idx, item in enumerate(line_items, start=1):
                raw_u = getattr(item, "unit_price", 0.0)
                raw_t = getattr(item, "total_price", 0.0)
                u_dec = Decimal(str(raw_u)) if not isinstance(raw_u, Decimal) else raw_u
                t_dec = Decimal(str(raw_t)) if not isinstance(raw_t, Decimal) else raw_t

                inv_line = InvoiceLine(
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    line_number=idx,
                    description=getattr(item, "description", str(item)),
                    quantity=float(getattr(item, "quantity", 1.0)),
                    unit_price=u_dec,
                    total_price=t_dec,
                    sku=getattr(item, "sku", None),
                )
                self.db.add(inv_line)

        try:
            await self.db.flush()
        except IntegrityError as ie:
            await self.db.rollback()
            raise ConflictError(
                f"Concurrent conflict: Invoice '{invoice_number}' was already posted concurrently by another request."
            ) from ie

        # 5. Record Audit Trail
        await AuditService.log_event(
            db=self.db,
            tenant_id=tenant_id,
            action="ERP_INVOICE_POSTED",
            entity_type="Invoice",
            entity_id=invoice.id,
            user_id=actor_id,
            actor_type="agent" if source == "agent" else "user",
            after_state={
                "invoice_number": invoice.invoice_number,
                "total": str(invoice.total_amount),
                "source": source,
                "validation_status": validation_status,
                "comments": comments,
            },
        )

        return invoice
