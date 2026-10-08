import json
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import require_permission
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.document import Document
from app.models.extraction import DocumentExtraction
from app.models.review import ReviewAction, ReviewTask
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.schemas.extraction import InvoiceExtractionSchema
from app.schemas.review import ReviewActionRequest, ReviewDecisionResponse, ReviewTaskResponse
from app.services.audit.service import AuditService
from app.services.erp.service import ERPService
from app.services.validation.policies import allowed_review_transition, requires_high_value_approval
from app.services.validation.engine import ValidationEngine

router = APIRouter(prefix="/reviews", tags=["Human Review"])


@router.get("", response_model=List[ReviewTaskResponse])
async def list_review_tasks(
    current_user: User = Depends(require_permission(Permission.REVIEW_READ)),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query("PENDING", alias="status"),
):
    """Lists human review tasks filtered by status."""
    stmt = (
        select(ReviewTask)
        .options(
            selectinload(ReviewTask.document).selectinload(Document.extraction),
            selectinload(ReviewTask.document).selectinload(Document.pages),
        )
        .where(ReviewTask.tenant_id == current_user.tenant_id)
        .order_by(desc(ReviewTask.created_at))
    )
    if status_filter:
        stmt = stmt.where(ReviewTask.status == status_filter)

    res = await db.execute(stmt)
    tasks = res.scalars().all()
    return [ReviewTaskResponse.model_validate(t) for t in tasks]


@router.get("/{task_id}", response_model=ReviewTaskResponse)
async def get_review_task(
    task_id: str,
    current_user: User = Depends(require_permission(Permission.REVIEW_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves full details for a review task including document evidence and extracted fields."""
    stmt = (
        select(ReviewTask)
        .options(
            selectinload(ReviewTask.document).selectinload(Document.extraction),
            selectinload(ReviewTask.document).selectinload(Document.pages),
        )
        .where(ReviewTask.id == task_id, ReviewTask.tenant_id == current_user.tenant_id)
    )
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise NotFoundError("ReviewTask", task_id)

    return ReviewTaskResponse.model_validate(task)


@router.post("/{task_id}/approve", response_model=ReviewDecisionResponse)
async def approve_review_task(
    task_id: str,
    body: ReviewActionRequest,
    current_user: User = Depends(require_permission(Permission.REVIEW_APPROVE)),
    db: AsyncSession = Depends(get_db),
):
    """
    Reviewer approves the document exception. Updates review state,
    posts invoice to simulated ERP system, marks document as COMPLETED, and records audit trail.
    """
    stmt = select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.tenant_id == current_user.tenant_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise NotFoundError("ReviewTask", task_id)

    # 1. State machine transition check
    if not allowed_review_transition(task.status, "RESOLVED"):
        raise ValidationError(
            f"Cannot approve task '{task_id}': transition from terminal status '{task.status}' to 'RESOLVED' is not permitted."
        )

    # 2. Load document and extraction by document_id + tenant_id
    doc_stmt = select(Document).where(Document.id == task.document_id, Document.tenant_id == current_user.tenant_id)
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document", task.document_id)

    ext_stmt = select(DocumentExtraction).where(
        DocumentExtraction.document_id == task.document_id, DocumentExtraction.tenant_id == current_user.tenant_id
    )
    ext = (await db.execute(ext_stmt)).scalar_one_or_none()
    data = {}
    if ext and ext.structured_data:
        data = json.loads(ext.structured_data) if isinstance(ext.structured_data, str) else ext.structured_data

        # 3. Parse total with Decimal and check high-value threshold
        total_val = data.get("total", 0.0)
        try:
            total_dec = Decimal(str(total_val))
        except Exception:
            total_dec = Decimal("0.00")

        if requires_high_value_approval(total_dec) and current_user.role not in ("admin", "ops_manager"):
            raise ForbiddenError(
                f"Invoice total (${total_dec:,.2f}) meets or exceeds the $10,000 policy threshold and strictly requires Operations Manager or Admin sign-off."
            )

        # 4. Re-run deterministic validation before ERP side effect
        try:
            validated_invoice = InvoiceExtractionSchema.model_validate(data)
            validator = ValidationEngine(db)
            confidences = {}
            if ext.field_confidences:
                try:
                    confidences = (
                        json.loads(ext.field_confidences)
                        if isinstance(ext.field_confidences, str)
                        else ext.field_confidences
                    )
                except Exception:
                    confidences = {}
            val_res = await validator.validate_invoice(
                tenant_id=current_user.tenant_id,
                extraction=validated_invoice,
                field_confidences=confidences,
            )
            if not val_res.is_clean and any(f.severity == "ERROR" for f in val_res.findings):
                if current_user.role not in ("admin", "ops_manager"):
                    raise ValidationError(
                        f"Validation policy error prevented approval: {val_res.routing_reason}. Explicit override requires manager or admin authority."
                    )
        except (ForbiddenError, ValidationError):
            raise
        except Exception as e:
            raise ValidationError(f"Pre-approval validation failed: {str(e)}")

    task.status = "RESOLVED"
    task.assigned_to_user_id = current_user.id
    task.resolution_notes = body.comments or "Approved by human reviewer."

    # Record ReviewAction
    act = ReviewAction(
        tenant_id=current_user.tenant_id,
        review_task_id=task.id,
        user_id=current_user.id,
        action="APPROVE",
        comments=body.comments,
    )
    db.add(act)

    # Update Document status
    doc.status = "APPROVED"

    # Post or update Invoice in ERP via centralized ERPService
    if ext and data:
        erp_service = ERPService(db)
        await erp_service.post_invoice(
            tenant_id=current_user.tenant_id,
            document_id=task.document_id,
            invoice_number=data.get("invoice_number", "INV-APPROVED"),
            vendor_name=data.get("vendor_name", "Vendor"),
            po_number=data.get("po_number"),
            total_amount=data.get("total", 0.0),
            currency=data.get("currency", "USD"),
            source="human",
            actor_id=current_user.id,
            validation_status="HUMAN_OVERRIDE_APPROVED",
            comments=body.comments,
        )

    # Resume workflow run if present
    if task.workflow_run_id:
        wf_stmt = select(WorkflowRun).where(
            WorkflowRun.id == task.workflow_run_id, WorkflowRun.tenant_id == current_user.tenant_id
        )
        wf = (await db.execute(wf_stmt)).scalar_one_or_none()
        if wf:
            wf.status = "COMPLETED"
            wf.result_summary = "Approved and resumed by human reviewer."

    await db.commit()

    # Log audit event
    await AuditService.log_event(
        db=db,
        tenant_id=current_user.tenant_id,
        action="REVIEW_TASK_APPROVED",
        entity_type="ReviewTask",
        entity_id=task.id,
        user_id=current_user.id,
        after_state={"comments": body.comments, "document_id": task.document_id},
    )

    return ReviewDecisionResponse(
        message="Review approved successfully. Invoice posted to ERP.",
        task_id=task.id,
        status="RESOLVED",
        workflow_status="COMPLETED",
    )


@router.post("/{task_id}/reject", response_model=ReviewDecisionResponse)
async def reject_review_task(
    task_id: str,
    body: ReviewActionRequest,
    current_user: User = Depends(require_permission(Permission.REVIEW_REJECT)),
    db: AsyncSession = Depends(get_db),
):
    """Reviewer rejects the document."""
    stmt = select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.tenant_id == current_user.tenant_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise NotFoundError("ReviewTask", task_id)

    if not allowed_review_transition(task.status, "REJECTED"):
        raise ValidationError(
            f"Cannot reject task '{task_id}': transition from terminal status '{task.status}' to 'REJECTED' is not permitted."
        )

    task.status = "REJECTED"
    task.assigned_to_user_id = current_user.id
    task.resolution_notes = body.comments or "Rejected by human reviewer."

    act = ReviewAction(
        tenant_id=current_user.tenant_id,
        review_task_id=task.id,
        user_id=current_user.id,
        action="REJECT",
        comments=body.comments,
    )
    db.add(act)

    doc_stmt = select(Document).where(Document.id == task.document_id, Document.tenant_id == current_user.tenant_id)
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if doc:
        doc.status = "REJECTED"

    if task.workflow_run_id:
        wf_stmt = select(WorkflowRun).where(
            WorkflowRun.id == task.workflow_run_id, WorkflowRun.tenant_id == current_user.tenant_id
        )
        wf = (await db.execute(wf_stmt)).scalar_one_or_none()
        if wf:
            wf.status = "FAILED"
            wf.result_summary = f"Rejected by reviewer: {body.comments}"

    await db.commit()

    await AuditService.log_event(
        db=db,
        tenant_id=current_user.tenant_id,
        action="REVIEW_TASK_REJECTED",
        entity_type="ReviewTask",
        entity_id=task.id,
        user_id=current_user.id,
        after_state={"comments": body.comments},
    )

    return ReviewDecisionResponse(
        message="Review rejected.",
        task_id=task.id,
        status="REJECTED",
        workflow_status="FAILED",
    )


@router.post("/{task_id}/edit", response_model=ReviewDecisionResponse)
async def edit_and_approve_review_task(
    task_id: str,
    body: ReviewActionRequest,
    current_user: User = Depends(require_permission(Permission.REVIEW_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    """
    Reviewer modifies extracted field values (e.g. correcting OCR errors),
    saves corrections, approves document, and updates ERP record.
    """
    stmt = select(ReviewTask).where(ReviewTask.id == task_id, ReviewTask.tenant_id == current_user.tenant_id)
    task = (await db.execute(stmt)).scalar_one_or_none()
    if not task:
        raise NotFoundError("ReviewTask", task_id)

    if not allowed_review_transition(task.status, "RESOLVED"):
        raise ValidationError(
            f"Cannot edit and approve task '{task_id}': transition from terminal status '{task.status}' to 'RESOLVED' is not permitted."
        )

    edited = body.edited_fields or {}

    # Update DocumentExtraction structured data
    ext_stmt = select(DocumentExtraction).where(
        DocumentExtraction.document_id == task.document_id, DocumentExtraction.tenant_id == current_user.tenant_id
    )
    ext = (await db.execute(ext_stmt)).scalar_one_or_none()
    if not ext:
        raise NotFoundError("DocumentExtraction", task.document_id)

    current_data = json.loads(ext.structured_data)
    current_data.update(edited)

    # 1. Re-validate through Pydantic InvoiceExtractionSchema
    try:
        validated_invoice = InvoiceExtractionSchema.model_validate(current_data)
    except Exception as val_err:
        raise ValidationError(f"Edited fields failed schema validation: {str(val_err)}")

    # 2. Re-run deterministic ValidationEngine
    validator = ValidationEngine(db)
    confidences = {}
    if ext.field_confidences:
        try:
            confidences = (
                json.loads(ext.field_confidences) if isinstance(ext.field_confidences, str) else ext.field_confidences
            )
        except Exception:
            confidences = {}
    val_res = await validator.validate_invoice(
        tenant_id=current_user.tenant_id,
        extraction=validated_invoice,
        field_confidences=confidences,
    )

    # 3. Check role authorization on high-value threshold using Decimal
    total_dec = Decimal(str(validated_invoice.total))
    if requires_high_value_approval(total_dec) and current_user.role not in ("admin", "ops_manager"):
        raise ForbiddenError(
            f"Edited invoice total (${total_dec:,.2f}) meets or exceeds the $10,000 policy threshold and strictly requires Operations Manager or Admin sign-off."
        )

    # 4. Update DocumentExtraction with revalidated state and findings
    ext.structured_data = json.dumps(validated_invoice.model_dump())
    ext.is_valid = val_res.is_clean
    ext.validation_findings = json.dumps([f.model_dump() for f in val_res.findings])

    # 5. Post to ERP via centralized ERPService
    erp_service = ERPService(db)
    await erp_service.post_invoice(
        tenant_id=current_user.tenant_id,
        document_id=task.document_id,
        invoice_number=validated_invoice.invoice_number,
        vendor_name=validated_invoice.vendor_name,
        po_number=validated_invoice.po_number,
        total_amount=validated_invoice.total,
        currency=validated_invoice.currency,
        source="human",
        actor_id=current_user.id,
        validation_status="HUMAN_EDITED_APPROVED",
        line_items=validated_invoice.line_items,
        comments=body.comments,
    )

    task.status = "RESOLVED"
    task.assigned_to_user_id = current_user.id
    task.resolution_notes = f"Edited fields: {list(edited.keys())}. {body.comments or ''}"

    act = ReviewAction(
        tenant_id=current_user.tenant_id,
        review_task_id=task.id,
        user_id=current_user.id,
        action="EDIT",
        comments=body.comments,
        field_diffs=json.dumps(edited),
    )
    db.add(act)

    doc_stmt = select(Document).where(Document.id == task.document_id, Document.tenant_id == current_user.tenant_id)
    doc = (await db.execute(doc_stmt)).scalar_one_or_none()
    if doc:
        doc.status = "COMPLETED"

    # Resume workflow run if present
    if task.workflow_run_id:
        wf_stmt = select(WorkflowRun).where(
            WorkflowRun.id == task.workflow_run_id, WorkflowRun.tenant_id == current_user.tenant_id
        )
        wf = (await db.execute(wf_stmt)).scalar_one_or_none()
        if wf:
            wf.status = "COMPLETED"
            wf.result_summary = "Edited, revalidated, and approved by human reviewer."

    await db.commit()

    await AuditService.log_event(
        db=db,
        tenant_id=current_user.tenant_id,
        action="REVIEW_TASK_EDITED_AND_APPROVED",
        entity_type="ReviewTask",
        entity_id=task.id,
        user_id=current_user.id,
        after_state={"diffs": edited, "comments": body.comments},
    )

    return ReviewDecisionResponse(
        message="Corrections saved and approved successfully.",
        task_id=task.id,
        status="RESOLVED",
        workflow_status="COMPLETED",
    )
