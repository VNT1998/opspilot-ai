import json
import re
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import Citation, KnowledgeSearchResponse
from app.services.llm.base import LLMProvider
from app.services.rag.chunker import chunk_document_text


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def lexical_score(query: str, text: str) -> float:
    query_tokens = set(re.findall(r"\w+", query.lower()))
    text_tokens = set(re.findall(r"\w+", text.lower()))
    if not query_tokens:
        return 0.0
    intersection = query_tokens.intersection(text_tokens)
    return len(intersection) / len(query_tokens)


class RAGEngine:
    """Enterprise RAG engine supporting hybrid retrieval, ACL filtering, and citations."""

    def __init__(self, db: AsyncSession, llm_provider: LLMProvider):
        self.db = db
        self.llm = llm_provider

    async def index_document(
        self,
        tenant_id: str,
        title: str,
        content: str,
        doc_type: str = "policy",
        department: str = "finance",
        acl_roles: Optional[List[str]] = None,
    ) -> KnowledgeDocument:
        roles = acl_roles or ["admin", "ops_manager", "reviewer", "viewer"]
        doc = KnowledgeDocument(
            tenant_id=tenant_id,
            title=title,
            doc_type=doc_type,
            department=department,
            content=content,
            acl_roles_json=json.dumps(roles),
        )
        self.db.add(doc)
        await self.db.flush()

        chunks = chunk_document_text(content)
        for chunk in chunks:
            embedding = await self.llm.embed(chunk.text)
            kchunk = KnowledgeChunk(
                tenant_id=tenant_id,
                document_id=doc.id,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                text=chunk.text,
                embedding_json=json.dumps(embedding),
                metadata_json=json.dumps({"title": title, "department": department, "doc_type": doc_type}),
            )
            self.db.add(kchunk)

        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def hybrid_search(
        self,
        tenant_id: str,
        query: str,
        user_role: str,
        limit: int = 4,
        doc_type: Optional[str] = None,
        department: Optional[str] = None,
    ) -> KnowledgeSearchResponse:
        """
        Executes ACL-aware hybrid search combining dense vector embeddings and lexical match.
        """
        query_embedding = await self.llm.embed(query)

        # Retrieve all chunks belonging to the tenant joined with knowledge document
        stmt = (
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeChunk.tenant_id == tenant_id)
        )
        if doc_type:
            stmt = stmt.where(KnowledgeDocument.doc_type == doc_type)
        if department:
            stmt = stmt.where(KnowledgeDocument.department == department)

        result = await self.db.execute(stmt)
        rows = result.all()

        scored_candidates: List[Tuple[float, KnowledgeChunk, KnowledgeDocument]] = []

        for chunk, doc in rows:
            # Enforce ACL: verify if user's role is in document's permitted ACL
            permitted_roles = json.loads(doc.acl_roles_json)
            if user_role not in permitted_roles and "admin" not in user_role:
                continue

            # 1. Dense vector similarity
            dense_score = 0.0
            if chunk.embedding_json:
                chunk_vec = json.loads(chunk.embedding_json)
                dense_score = cosine_similarity(query_embedding, chunk_vec)

            # 2. Lexical keyword score
            lex_score = lexical_score(query, chunk.text)

            # 3. Hybrid fusion score (70% dense + 30% lexical)
            hybrid_score = (0.7 * dense_score) + (0.3 * lex_score)
            scored_candidates.append((hybrid_score, chunk, doc))

        # Sort by hybrid score descending
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_candidates[:limit]

        citations: List[Citation] = []
        context_snippets: List[str] = []

        for score, chunk, doc in top_candidates:
            # Extract most relevant snippet / first 250 chars
            snippet = chunk.text[:250].strip() + ("..." if len(chunk.text) > 250 else "")
            citations.append(
                Citation(
                    document_id=doc.id,
                    chunk_id=chunk.id,
                    title=doc.title,
                    page_number=chunk.page_number,
                    snippet=snippet,
                    relevance_score=round(score, 3),
                )
            )
            context_snippets.append(f"[{doc.title} - Page {chunk.page_number}]: {chunk.text}")

        # Assemble context for synthesis
        context_block = "\n\n".join(context_snippets)
        prompt = (
            f"Based STRICTLY on the following company knowledge sources, answer the question accurately.\n"
            f"Sources:\n{context_block}\n\n"
            f"Question: {query}\n\n"
            f"Answer:"
        )

        if not context_snippets:
            answer = "No applicable policy or documentation found matching your search and role authorization."
        else:
            answer = await self.llm.generate(prompt)

        return KnowledgeSearchResponse(
            query=query,
            answer=answer,
            sources=citations,
        )
