from typing import List, Optional
from pydantic import BaseModel


class Citation(BaseModel):
    document_id: str
    chunk_id: Optional[str] = None
    title: str
    page_number: int
    snippet: str
    relevance_score: float


class KnowledgeIndexRequest(BaseModel):
    title: str
    content: str
    doc_type: str = "policy"
    department: str = "finance"
    acl_roles: List[str] = ["admin", "ops_manager", "reviewer", "viewer"]


class KnowledgeSearchRequest(BaseModel):
    query: str
    limit: int = 4
    doc_type: Optional[str] = None
    department: Optional[str] = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    answer: str
    sources: List[Citation]
