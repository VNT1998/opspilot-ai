from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import require_permission
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.erp import Invoice, PurchaseOrder, Vendor
from app.models.user import User

router = APIRouter(prefix="/erp", tags=["Simulated ERP System"])


@router.get("/purchase-orders")
async def list_purchase_orders(
    current_user: User = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.tenant_id == current_user.tenant_id)
    )
    pos = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": p.id,
            "po_number": p.po_number,
            "vendor_name": p.vendor_name,
            "total_amount": p.total_amount,
            "currency": p.currency,
            "status": p.status,
            "lines": [
                {
                    "line_number": l.line_number,
                    "description": l.description,
                    "quantity": l.quantity,
                    "unit_price": l.unit_price,
                    "total_price": l.total_price,
                    "sku": l.sku,
                }
                for l in p.lines
            ],
        }
        for p in pos
    ]


@router.get("/vendors")
async def list_vendors(
    current_user: User = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Vendor).where(Vendor.tenant_id == current_user.tenant_id)
    vnds = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": v.id,
            "name": v.name,
            "vendor_code": v.vendor_code,
            "payment_terms": v.payment_terms,
            "is_approved": v.is_approved,
        }
        for v in vnds
    ]


@router.get("/invoices")
async def list_erp_invoices(
    current_user: User = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Invoice).where(Invoice.tenant_id == current_user.tenant_id)
    invs = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": i.id,
            "invoice_number": i.invoice_number,
            "vendor_name": i.vendor_name,
            "po_number": i.po_number,
            "total_amount": i.total_amount,
            "currency": i.currency,
            "status": i.status,
            "validation_status": i.validation_status,
            "created_at": i.created_at,
        }
        for i in invs
    ]
