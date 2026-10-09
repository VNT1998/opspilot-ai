import json
from unittest.mock import AsyncMock, patch
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.outbox import DocumentOutbox, OutboxStatus
from app.models.workflow import WorkflowRun
from app.services.queue.in_memory import InMemoryQueueBackend
from app.services.queue.redis import RedisQueueBackend
from app.services.queue.worker import JobQueueWorker


@pytest.mark.asyncio
async def test_in_memory_queue_enqueue_dequeue_and_dlq():
    """In-memory queue implements durable queue contract with DLQ."""
    backend = InMemoryQueueBackend()
    payload = {"job_id": "job_1", "document_id": "doc_1", "tenant_id": "tenant_1"}

    await backend.enqueue(payload)
    depth = await backend.get_depth()
    assert depth == 1

    deq_payload = await backend.dequeue()
    assert deq_payload is not None
    assert deq_payload["job_id"] == "job_1"
    assert deq_payload["document_id"] == "doc_1"
    assert "_message_id" in deq_payload

    # Send to DLQ on repeated failure
    deq_payload["failure_reason"] = "Exceeded retry limit"
    await backend.enqueue_dlq(deq_payload, reason="Exceeded retry limit")
    dlq_depth = await backend.get_dlq_depth()
    assert dlq_depth == 1

    # Main queue and in-flight are now empty
    assert await backend.get_depth() == 0


@pytest.mark.asyncio
async def test_redis_queue_configuration():
    """RedisQueueBackend configuration and queue keys match durable spec."""
    backend = RedisQueueBackend(redis_url="redis://localhost:6379/0")
    assert backend.stream_name == "opspilot:stream:jobs"
    assert backend.group_name == "opspilot:workers"
    assert backend.dlq_name == "opspilot:queue:dlq"


@pytest.mark.asyncio
async def test_worker_crash_and_pending_job_reclaim():
    """
    When a worker dequeues a message and crashes before acknowledging (ack),
    reclaim_pending() recovers the job from in-flight/PEL and redelivers it.
    """
    backend = InMemoryQueueBackend()
    job = {"workflow_run_id": "wf_crash_1", "document_id": "doc_1", "attempt": 1}

    msg_id = await backend.enqueue(job)
    assert await backend.get_depth() == 1

    # Worker 1 dequeues the job
    worker_1_job = await backend.dequeue()
    assert worker_1_job is not None
    assert worker_1_job["workflow_run_id"] == "wf_crash_1"
    assert worker_1_job["_message_id"] == msg_id

    # Queue ready is 0, but in-flight is 1 (depth is 1)
    assert await backend.get_depth() == 1

    # Worker 1 "dies" before calling backend.ack()
    # At this moment, another dequeue gets nothing because job is pending in-flight
    second_deq = await backend.dequeue(timeout=0.01)
    assert second_deq is None

    # Dead-worker recovery runs: reclaim with min_idle_ms=0
    reclaimed = await backend.reclaim_pending(min_idle_ms=0)
    assert len(reclaimed) == 1
    assert reclaimed[0]["workflow_run_id"] == "wf_crash_1"

    # Worker 2 now successfully dequeues the reclaimed job and finishes
    worker_2_job = await backend.dequeue()
    assert worker_2_job is not None
    assert worker_2_job["workflow_run_id"] == "wf_crash_1"

    # Worker 2 commits and calls ack()
    await backend.ack(worker_2_job["_message_id"])

    # Now queue is completely cleared
    assert await backend.get_depth() == 0


@pytest.mark.asyncio
async def test_reliable_outbox_persistence_and_reconciliation(db_session: AsyncSession):
    """
    When immediate queue enqueue fails (e.g. Redis connection timeout),
    DocumentOutbox preserves the job as PENDING and reconciler successfully dispatches it.
    """
    doc = Document(
        id="doc_outbox_test_1",
        tenant_id="tenant_test",
        filename="invoice_outbox.pdf",
        file_type="pdf",
        file_size=500,
        mime_type="application/pdf",
        storage_path="mock/invoice_outbox.pdf",
        status="PENDING_DISPATCH",
    )
    db_session.add(doc)
    await db_session.commit()

    # Create a failing queue backend to simulate Redis network outage
    failing_backend = InMemoryQueueBackend()
    failing_backend.enqueue = AsyncMock(side_effect=ConnectionError("Redis connection refused"))

    worker = JobQueueWorker(backend=failing_backend)

    # Calling enqueue_job creates outbox row even if backend.enqueue fails
    wf_id = await worker.enqueue_job(
        document_id=doc.id,
        tenant_id="tenant_test",
        user_id="usr_1",
        user_role="admin",
    )

    # Verify outbox row exists in PENDING state with last_error recorded
    stmt = select(DocumentOutbox).where(DocumentOutbox.workflow_run_id == wf_id)
    outbox_entry = (await db_session.execute(stmt)).scalar_one()
    assert outbox_entry.status == OutboxStatus.PENDING.value
    assert "Redis connection refused" in (outbox_entry.last_error or "")

    # Now simulate Redis recovery: provide working backend and run outbox reconciler
    working_backend = InMemoryQueueBackend()
    worker.backend = working_backend

    reconciled_count = await worker.reconcile_outbox()
    assert reconciled_count == 1

    # Outbox is now DISPATCHED
    await db_session.refresh(outbox_entry)
    assert outbox_entry.status == OutboxStatus.DISPATCHED.value
    assert outbox_entry.dispatched_at is not None

    # Working queue received the job
    assert await working_backend.get_depth() == 1
    dequeued = await working_backend.dequeue()
    assert dequeued["workflow_run_id"] == wf_id


@pytest.mark.asyncio
async def test_retry_rescheduled_through_queue_without_worker_blocking(db_session: AsyncSession):
    """Retrying jobs reschedule through the queue rather than blocking worker thread."""
    doc = Document(
        id="doc_retry_test_1",
        tenant_id="tenant_test",
        filename="failing_doc.pdf",
        file_type="pdf",
        file_size=500,
        mime_type="application/pdf",
        storage_path="mock/failing_doc.pdf",
        status="QUEUED",
    )
    wf = WorkflowRun(
        id="wf_retry_test_1",
        tenant_id="tenant_test",
        document_id=doc.id,
        status="PENDING",
    )
    db_session.add_all([doc, wf])
    await db_session.commit()

    backend = InMemoryQueueBackend()
    worker = JobQueueWorker(backend=backend)

    # Process job where execution fails on attempt 1
    job = {
        "workflow_run_id": wf.id,
        "document_id": doc.id,
        "tenant_id": "tenant_test",
        "user_id": "usr_1",
        "user_role": "reviewer",
        "attempt": 1,
        "max_attempts": 3,
        "_message_id": "msg_att_1",
    }
    backend._in_flight["msg_att_1"] = job

    from app.services.parsing.result import ParsedDocument, ParsedPage

    dummy_doc = ParsedDocument(
        text="Invoice: INV-100",
        pages=[ParsedPage(page_number=1, text="Invoice: INV-100", confidence=0.99)],
        parser="mock",
        parser_version="1.0",
    )

    with (
        patch("app.services.queue.worker.get_storage_provider") as mock_storage_factory,
        patch("app.services.parsing.router.get_document_parser_router") as mock_router_factory,
        patch("app.services.agents.graph.AgentWorkflowService.execute_workflow", side_effect=ValueError("LLM timeout")),
    ):
        mock_storage = AsyncMock()
        mock_storage.get_file.return_value = b"%PDF-1.4 dummy"
        mock_storage_factory.return_value = mock_storage
        mock_router = AsyncMock()
        mock_router.parse_document.return_value = dummy_doc
        mock_router_factory.return_value = mock_router

        await worker._process_single_job(job)

    # Old message was acknowledged (removed from in-flight)
    assert "msg_att_1" not in backend._in_flight

    # Next attempt was scheduled back into the queue with attempt 2
    assert await backend.get_depth() == 1
    next_job = await backend.dequeue()
    assert next_job["attempt"] == 2


@pytest.mark.asyncio
async def test_exhausted_retries_routed_to_dlq(db_session: AsyncSession):
    """Exhausted retries route to DLQ with diagnostic reason and mark document FAILED."""
    doc = Document(
        id="doc_dlq_test_1",
        tenant_id="tenant_test",
        filename="dlq_doc.pdf",
        file_type="pdf",
        file_size=500,
        mime_type="application/pdf",
        storage_path="mock/dlq_doc.pdf",
        status="QUEUED",
    )
    wf = WorkflowRun(
        id="wf_dlq_test_1",
        tenant_id="tenant_test",
        document_id=doc.id,
        status="PENDING",
    )
    db_session.add_all([doc, wf])
    await db_session.commit()

    backend = InMemoryQueueBackend()
    worker = JobQueueWorker(backend=backend)

    # Job on its final attempt
    job = {
        "workflow_run_id": wf.id,
        "document_id": doc.id,
        "tenant_id": "tenant_test",
        "user_id": "usr_1",
        "user_role": "reviewer",
        "attempt": 3,
        "max_attempts": 3,
        "_message_id": "msg_dlq_1",
    }
    backend._in_flight["msg_dlq_1"] = job

    from app.services.parsing.result import ParsedDocument, ParsedPage

    dummy_doc = ParsedDocument(
        text="Invoice: INV-100",
        pages=[ParsedPage(page_number=1, text="Invoice: INV-100", confidence=0.99)],
        parser="mock",
        parser_version="1.0",
    )

    with (
        patch("app.services.queue.worker.get_storage_provider") as mock_storage_factory,
        patch("app.services.parsing.router.get_document_parser_router") as mock_router_factory,
        patch(
            "app.services.agents.graph.AgentWorkflowService.execute_workflow",
            side_effect=RuntimeError("Permanent corruption"),
        ),
    ):
        mock_storage = AsyncMock()
        mock_storage.get_file.return_value = b"%PDF-1.4 dummy"
        mock_storage_factory.return_value = mock_storage
        mock_router = AsyncMock()
        mock_router.parse_document.return_value = dummy_doc
        mock_router_factory.return_value = mock_router

        await worker._process_single_job(job)

    # DLQ received the job with diagnostic reason
    assert await backend.get_dlq_depth() == 1
    dlq_item = backend._dlq[0]
    assert dlq_item["workflow_run_id"] == wf.id
    assert "Permanent corruption" in dlq_item["dlq_reason"]

    # Document and workflow are marked FAILED
    await db_session.refresh(doc)
    await db_session.refresh(wf)
    assert doc.status == "FAILED"
    assert wf.status == "FAILED"
    assert wf.failure_code == "PIPELINE_ERROR"


@pytest.mark.asyncio
async def test_redis_streams_backend_operations():
    """RedisQueueBackend executes Redis Streams commands (XADD, XREADGROUP, XACK, XAUTOCLAIM)."""
    mock_redis = AsyncMock()
    mock_redis.xgroup_create = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value="1690000000000-0")
    mock_redis.xreadgroup = AsyncMock(
        return_value=[("opspilot:stream:jobs", [("1690000000000-0", {"payload": json.dumps({"job_id": "redis_1"})})])]
    )
    mock_redis.xack = AsyncMock(return_value=1)
    mock_redis.xautoclaim = AsyncMock(
        return_value=["0-0", [("1690000000000-1", {"payload": json.dumps({"job_id": "reclaimed_1"})})], []]
    )
    mock_redis.xlen = AsyncMock(return_value=5)

    backend = RedisQueueBackend(redis_url="redis://localhost:6379/0")
    backend._client = mock_redis
    backend._group_created = True

    # Enqueue calls XADD
    msg_id = await backend.enqueue({"job_id": "redis_1"})
    assert msg_id == "1690000000000-0"
    mock_redis.xadd.assert_awaited_once()

    # Dequeue calls XREADGROUP
    deq = await backend.dequeue(timeout=0.1)
    assert deq["job_id"] == "redis_1"
    assert deq["_message_id"] == "1690000000000-0"

    # Ack calls XACK
    await backend.ack("1690000000000-0")
    mock_redis.xack.assert_awaited_once_with("opspilot:stream:jobs", "opspilot:workers", "1690000000000-0")

    # Reclaim calls XAUTOCLAIM
    reclaimed = await backend.reclaim_pending(min_idle_ms=30000)
    assert len(reclaimed) == 1
    assert reclaimed[0]["job_id"] == "reclaimed_1"
    assert reclaimed[0]["_message_id"] == "1690000000000-1"


@pytest.mark.asyncio
async def test_live_redis_streams_durability_if_available():
    """
    Integration test against live Redis instance (e.g. running in CI service container).
    Tests XADD, XREADGROUP, XACK, PEL reclamation, and DLQ.
    Skips automatically if Redis is unreachable.
    """
    import os
    import redis.asyncio as aioredis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
    except Exception:
        pytest.skip(f"Live Redis not accessible at {redis_url}")

    stream_key = "opspilot:test:stream:jobs"
    dlq_key = "opspilot:test:queue:dlq"
    group_name = "opspilot:test:group"
    # Clean up prior test runs
    await client.delete(stream_key, dlq_key)

    backend = RedisQueueBackend(redis_url=redis_url)
    backend.stream_name = stream_key
    backend.dlq_name = dlq_key
    backend.group_name = group_name

    try:
        # Enqueue job
        msg_id = await backend.enqueue({"job_id": "live_job_1", "doc": "live_doc_1"})
        assert msg_id is not None
        assert await backend.get_depth() == 1

        # Dequeue job
        job = await backend.dequeue(timeout=1.0)
        assert job is not None
        assert job["job_id"] == "live_job_1"
        assert job["_message_id"] == msg_id

        # Reclaim pending with min_idle_ms=0 (PEL check)
        reclaimed = await backend.reclaim_pending(min_idle_ms=0)
        assert len(reclaimed) >= 1
        assert reclaimed[0]["job_id"] == "live_job_1"

        # Acknowledge
        await backend.ack(msg_id)

        # Enqueue to DLQ
        await backend.enqueue_dlq(job, reason="Live test failure")
        assert await backend.get_dlq_depth() == 1

    finally:
        await client.delete(stream_key, dlq_key)
        await client.aclose()
        if backend._client:
            await backend._client.aclose()
