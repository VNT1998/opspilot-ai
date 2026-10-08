import pytest
from app.services.queue.in_memory import InMemoryQueueBackend
from app.services.queue.redis import RedisQueueBackend


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

    # Send to DLQ on repeated failure
    deq_payload["failure_reason"] = "Exceeded retry limit"
    await backend.enqueue_dlq(deq_payload)
    dlq_depth = await backend.get_dlq_depth()
    assert dlq_depth == 1

    # Main queue is now empty
    assert await backend.get_depth() == 0


@pytest.mark.asyncio
async def test_redis_queue_configuration():
    """RedisQueueBackend configuration and queue keys match durable spec."""
    backend = RedisQueueBackend(redis_url="redis://localhost:6379/0")
    assert backend.queue_name == "opspilot:jobs"
    assert backend.dlq_name == "opspilot:dlq"
