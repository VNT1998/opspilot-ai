import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.workflow import AgentRun, WorkflowRun


@pytest.mark.asyncio
async def test_metrics_no_fake_confidence_fallback(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    """When tenant has documents without confidence scores, average confidence must not default to 0.94."""
    # Seed document with None confidence_score
    doc = Document(
        id="doc_no_conf",
        tenant_id="tenant_test",
        filename="unscored.pdf",
        file_type="pdf",
        file_size=100,
        mime_type="application/pdf",
        storage_path="mock/unscored.pdf",
        status="QUEUED",
        confidence_score=None,
    )
    db_session.add(doc)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/v1/metrics", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["avg_confidence_score"] == 0.0  # NOT 0.94!


@pytest.mark.asyncio
async def test_metrics_token_source_breakdown(
    client: AsyncClient,
    admin_token: str,
    db_session: AsyncSession,
):
    """Metrics clearly breaks down provider-reported vs estimated token usage."""
    wf = WorkflowRun(
        id="wf_met_1",
        tenant_id="tenant_test",
        document_id="doc_no_conf",
        status="COMPLETED",
    )
    db_session.add(wf)

    run_provider = AgentRun(
        id="ar_prov",
        tenant_id="tenant_test",
        workflow_run_id=wf.id,
        model="gpt-4o",
        provider="openai",
        usage_source="provider",
        input_tokens=150,
        output_tokens=50,
        total_cost=0.0003,
    )
    run_est = AgentRun(
        id="ar_est",
        tenant_id="tenant_test",
        workflow_run_id=wf.id,
        model="mock-agent-v1",
        provider="mock",
        usage_source="estimated",
        input_tokens=300,
        output_tokens=100,
        total_cost=0.0006,
    )
    db_session.add_all([run_provider, run_est])
    await db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    res = await client.get("/api/v1/metrics", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["provider_tokens"] == 200
    assert data["estimated_tokens"] == 400
    assert data["total_tokens_used"] == 600
