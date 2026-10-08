import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.llm.mock_provider import MockLLMProvider
from app.services.rag.engine import RAGEngine


@pytest.mark.asyncio
async def test_rag_indexing_and_hybrid_search(db_session: AsyncSession):
    llm = MockLLMProvider()
    rag = RAGEngine(db_session, llm)

    policy_text = """
--- Page 1 ---
Corporate Expense & Invoice Policy 2026.
Invoices under $5,000 are eligible for straight-through automated processing.
Invoices over $10,000 require manual CFO or Operations Manager sign-off.
    """
    await rag.index_document(
        tenant_id="tenant_test",
        title="Corporate Expense Policy",
        content=policy_text,
        doc_type="policy",
        department="finance",
        acl_roles=["admin", "ops_manager", "reviewer"],
    )

    # 1. Search as reviewer (allowed by ACL)
    search_res = await rag.hybrid_search(
        tenant_id="tenant_test",
        query="What is the approval policy for invoices over $10,000?",
        user_role="reviewer",
        limit=2,
    )
    assert len(search_res.sources) > 0
    assert search_res.sources[0].title == "Corporate Expense Policy"
    assert search_res.sources[0].relevance_score > 0.0

    # 2. Search as viewer (NOT allowed by ACL)
    denied_res = await rag.hybrid_search(
        tenant_id="tenant_test",
        query="What is the approval policy for invoices over $10,000?",
        user_role="viewer",
        limit=2,
    )
    assert len(denied_res.sources) == 0


@pytest.mark.asyncio
async def test_rag_chunk_provenance_and_metadata(db_session: AsyncSession):
    """Verifies that citations contain verifiable chunk_id and provenance metadata."""
    llm = MockLLMProvider()
    rag = RAGEngine(db_session, llm)

    content = """
--- Page 1 ---
Corporate Travel and Incidentals SOP.
Employees must book flights at least 14 days in advance.
--- Page 2 ---
Meal allowances are capped at $75 per day per person.
    """
    doc = await rag.index_document(
        tenant_id="tenant_test",
        title="Travel and Entertainment SOP",
        content=content,
        doc_type="sop",
        department="hr",
        acl_roles=["admin", "reviewer", "viewer"],
    )

    search_res = await rag.hybrid_search(
        tenant_id="tenant_test",
        query="What is the daily meal allowance limit?",
        user_role="reviewer",
        limit=2,
    )

    assert len(search_res.sources) > 0
    first_citation = search_res.sources[0]
    assert first_citation.document_id == doc.id
    assert first_citation.chunk_id is not None
    assert first_citation.title == "Travel and Entertainment SOP"
    assert first_citation.page_number in (1, 2)
    assert len(first_citation.snippet) > 0
    assert first_citation.relevance_score > 0.0


@pytest.mark.asyncio
async def test_rag_department_and_type_filtering(db_session: AsyncSession):
    """Verifies that filtering by department and doc_type strictly confines retrieval."""
    llm = MockLLMProvider()
    rag = RAGEngine(db_session, llm)

    await rag.index_document(
        tenant_id="tenant_test",
        title="Engineering Infrastructure Access Policy",
        content="Production AWS root access requires VP of Engineering sign-off.",
        doc_type="security_policy",
        department="engineering",
        acl_roles=["admin", "reviewer"],
    )

    await rag.index_document(
        tenant_id="tenant_test",
        title="Accounts Payable Wire Transfer Policy",
        content="All international wire transfers require CFO dual-approval.",
        doc_type="finance_policy",
        department="finance",
        acl_roles=["admin", "reviewer"],
    )

    # Search filtering by department='finance'
    fin_res = await rag.hybrid_search(
        tenant_id="tenant_test",
        query="wire transfer approval rules",
        user_role="reviewer",
        department="finance",
    )
    assert len(fin_res.sources) > 0
    assert all(s.title == "Accounts Payable Wire Transfer Policy" for s in fin_res.sources)

    # Search filtering by department='engineering'
    eng_res = await rag.hybrid_search(
        tenant_id="tenant_test",
        query="wire transfer approval rules",
        user_role="reviewer",
        department="engineering",
    )
    assert len(eng_res.sources) == 0


@pytest.mark.asyncio
async def test_rag_missing_document_graceful_handling(db_session: AsyncSession):
    """Verifies that queries over empty or unindexed knowledge bases return cleanly without error."""
    llm = MockLLMProvider()
    rag = RAGEngine(db_session, llm)

    search_res = await rag.hybrid_search(
        tenant_id="tenant_test",
        query="Hypersonic propulsion maintenance guidelines",
        user_role="reviewer",
        limit=5,
    )
    assert isinstance(search_res.sources, list)
    assert len(search_res.sources) == 0
    assert "No relevant policy documents" in search_res.answer or len(search_res.answer) > 0
