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


def test_pricing_calculation_separate_input_output():
    """calculate_call_cost uses separate input and output rates and returns zero for local models."""
    from app.services.llm.pricing import calculate_call_cost

    # gpt-4o: input $0.0025 / 1k, output $0.0100 / 1k
    # 2000 input = $0.005, 1000 output = $0.010 -> total $0.015
    cost_gpt4o = calculate_call_cost("gpt-4o", input_tokens=2000, output_tokens=1000)
    assert cost_gpt4o == 0.015

    # Local Ollama model has zero cloud billing cost
    cost_local = calculate_call_cost("medgemma:4b", input_tokens=2000, output_tokens=1000)
    assert cost_local == 0.0


@pytest.mark.asyncio
async def test_workflow_telemetry_captures_exact_usage(db_session: AsyncSession):
    """Workflow execution captures exact per-call usage on AgentRun without hardcoded defaults."""
    from app.models.document import Document
    from app.models.workflow import AgentRun, WorkflowRun
    from app.services.agents.graph import AgentWorkflowService
    from app.services.agents.state import OpsPilotState
    from app.services.llm.mock_provider import MockLLMProvider
    from sqlalchemy import select

    doc = Document(
        id="doc_usage_test_1",
        tenant_id="tenant_test",
        filename="usage_test.pdf",
        file_type="pdf",
        file_size=500,
        mime_type="application/pdf",
        storage_path="mock/usage_test.pdf",
        status="PROCESSING",
    )
    wf = WorkflowRun(
        id="wf_usage_test_1",
        tenant_id="tenant_test",
        document_id=doc.id,
        status="RUNNING",
    )
    db_session.add_all([doc, wf])
    await db_session.commit()

    provider = MockLLMProvider()
    svc = AgentWorkflowService(db_session, provider)

    state: OpsPilotState = {
        "tenant_id": "tenant_test",
        "user_id": "usr_reviewer_1",
        "user_role": "reviewer",
        "document_id": doc.id,
        "workflow_run_id": wf.id,
        "filename": "usage_test.pdf",
        "file_type": "pdf",
        "raw_text": "Invoice: INV-9901\nVendor: Acme Supplies\nPO: PO-9001\nTotal: $1450.00\nSubtotal: $1318.18\nTax: $131.82",
    }

    res = await svc.execute_workflow(state)
    assert res["usage_source"] == "estimated"
    assert res["total_tokens"] > 0
    assert res["total_cost"] > 0.0

    # Verify AgentRun was persisted with exact state values, not hardcoded 600 or 0.002
    stmt = select(AgentRun).where(AgentRun.workflow_run_id == wf.id)
    agent_run = (await db_session.execute(stmt)).scalar_one()
    assert agent_run.model == "mock-agent-v1"
    assert agent_run.provider == "mock"
    assert agent_run.usage_source == "estimated"
    assert agent_run.input_tokens == res["input_tokens"]
    assert agent_run.output_tokens == res["output_tokens"]
    assert agent_run.total_cost == res["total_cost"]
