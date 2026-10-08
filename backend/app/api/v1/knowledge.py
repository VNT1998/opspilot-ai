import json
from fastapi import APIRouter, Depends, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_permission
from app.core.rate_limit import rate_limit
from app.core.rbac import Permission
from app.db.session import get_db
from app.models.knowledge import KnowledgeDocument
from app.models.user import User
from app.schemas.knowledge import (
    KnowledgeIndexRequest,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.llm.factory import get_llm_provider
from app.services.rag.engine import RAGEngine

router = APIRouter(prefix="/knowledge", tags=["Knowledge & RAG"])


@router.post("/index", status_code=status.HTTP_201_CREATED)
async def index_knowledge_document(
    body: KnowledgeIndexRequest,
    current_user: User = Depends(require_permission(Permission.KNOWLEDGE_INDEX)),
    db: AsyncSession = Depends(get_db),
    _rl: bool = Depends(rate_limit(requests_per_minute=20)),
):
    """Chunks, embeds, and indexes a corporate policy/SOP document for ACL-gated retrieval."""
    llm = get_llm_provider()
    rag = RAGEngine(db, llm)

    doc = await rag.index_document(
        tenant_id=current_user.tenant_id,
        title=body.title,
        content=body.content,
        doc_type=body.doc_type,
        department=body.department,
        acl_roles=body.acl_roles,
    )

    return {
        "id": doc.id,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "department": doc.department,
        "message": "Knowledge document successfully indexed with vector embeddings.",
    }


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    body: KnowledgeSearchRequest,
    current_user: User = Depends(require_permission(Permission.KNOWLEDGE_SEARCH)),
    db: AsyncSession = Depends(get_db),
    _rl: bool = Depends(rate_limit(requests_per_minute=40)),
):
    """
    Executes ACL-aware hybrid search (dense vector + lexical match)
    over indexed company policies and returns synthesized answer with verifiable citations.
    """
    llm = get_llm_provider()
    rag = RAGEngine(db, llm)

    response = await rag.hybrid_search(
        tenant_id=current_user.tenant_id,
        query=body.query,
        user_role=current_user.role,
        limit=body.limit,
        doc_type=body.doc_type,
        department=body.department,
    )
    return response


@router.get("")
async def list_knowledge_documents(
    current_user: User = Depends(require_permission(Permission.KNOWLEDGE_SEARCH)),
    db: AsyncSession = Depends(get_db),
):
    """Lists indexed knowledge documents."""
    stmt = (
        select(KnowledgeDocument)
        .where(KnowledgeDocument.tenant_id == current_user.tenant_id)
        .order_by(desc(KnowledgeDocument.created_at))
    )
    docs = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "doc_type": d.doc_type,
            "department": d.department,
            "acl_roles": json.loads(d.acl_roles_json),
            "created_at": d.created_at,
        }
        for d in docs
    ]
