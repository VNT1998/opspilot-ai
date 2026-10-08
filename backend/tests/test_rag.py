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
