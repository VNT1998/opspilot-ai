import json
from pathlib import Path
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import get_current_user, require_permission
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.document import Document, DocumentPage
from app.models.user import User
from app.schemas.document import DocumentListResponse, DocumentReprocessRequest, DocumentResponse
from app.services.audit.service import AuditService
from app.services.queue.worker import get_job_worker
from app.services.storage.local import get_storage_provider

settings = get_settings()
router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(Permission.DOCUMENT_CREATE)),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingests a document file, persists it to storage, creates a database record,
    and enqueues an asynchronous processing job, returning 202 Accepted immediately.
    """
    ext = Path(file.filename or "upload.bin").suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise ValidationError(f"File extension '{ext}' is not supported. Allowed: {settings.ALLOWED_EXTENSIONS}")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise ValidationError(f"File size exceeds maximum permitted limit of {settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB")

    storage = get_storage_provider()
    storage_path = await storage.save_file(content, file.filename or "upload.bin", current_user.tenant_id)

    # Create Document record
    doc = Document(
        tenant_id=current_user.tenant_id,
        filename=file.filename or "uploaded_file",
        file_type=ext.replace(".", ""),
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        storage_path=storage_path,
        status="QUEUED",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Audit log
    await AuditService.log_event(
        db=db,
        tenant_id=current_user.tenant_id,
        action="DOCUMENT_UPLOADED",
        entity_type="Document",
        entity_id=doc.id,
        user_id=current_user.id,
        after_state={"filename": doc.filename, "size": doc.file_size},
    )

    # Enqueue processing job to asynchronous worker
    worker = get_job_worker()
    job_id = await worker.enqueue_job(
        document_id=doc.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "workflow_job_id": job_id,
        "message": "Document accepted for asynchronous processing.",
    }


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    current_user: User = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None, alias="status"),
    classification: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lists tenant documents with filtering and pagination."""
    stmt = (
        select(Document)
        .options(selectinload(Document.pages), selectinload(Document.extraction))
        .where(Document.tenant_id == current_user.tenant_id)
        .order_by(desc(Document.created_at))
    )
    if status_filter:
        stmt = stmt.where(Document.status == status_filter)
    if classification:
        stmt = stmt.where(Document.classification == classification)

    # Simple count & slice
    res = await db.execute(stmt)
    all_docs = res.scalars().all()
    total = len(all_docs)
    start_idx = (page - 1) * page_size
    paged_docs = all_docs[start_idx : start_idx + page_size]

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in paged_docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: User = Depends(require_permission(Permission.DOCUMENT_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves document details, extracted fields, and page breakdowns."""
    stmt = (
        select(Document)
        .options(selectinload(Document.pages), selectinload(Document.extraction))
        .where(Document.id == document_id, Document.tenant_id == current_user.tenant_id)
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document", document_id)

    return DocumentResponse.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: User = Depends(require_permission(Permission.DOCUMENT_DELETE)),
    db: AsyncSession = Depends(get_db),
):
    """Deletes a document and associated metadata."""
    stmt = select(Document).where(Document.id == document_id, Document.tenant_id == current_user.tenant_id)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document", document_id)

    storage = get_storage_provider()
    await storage.delete_file(doc.storage_path)

    await db.delete(doc)
    await db.commit()

    await AuditService.log_event(
        db=db,
        tenant_id=current_user.tenant_id,
        action="DOCUMENT_DELETED",
        entity_type="Document",
        entity_id=document_id,
        user_id=current_user.id,
    )


@router.post("/{document_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document(
    document_id: str,
    body: DocumentReprocessRequest,
    current_user: User = Depends(require_permission(Permission.DOCUMENT_REPROCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Re-enqueues a document for full processing through the AI agent pipeline."""
    stmt = select(Document).where(Document.id == document_id, Document.tenant_id == current_user.tenant_id)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document", document_id)

    doc.status = "QUEUED"
    await db.commit()

    worker = get_job_worker()
    job_id = await worker.enqueue_job(
        document_id=doc.id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )

    return {
        "id": doc.id,
        "status": "QUEUED",
        "workflow_job_id": job_id,
        "message": "Document re-enqueued for processing.",
    }
