import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional
from app.services.queue.base import BaseQueueBackend


class InMemoryQueueBackend(BaseQueueBackend):
    """
    In-memory queue for local development and deterministic tests.
    Faithfully simulates Redis Streams acknowledgement, pending PEL (in-flight) tracking,
    and dead-consumer job reclamation.
    """

    def __init__(self):
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._in_flight: Dict[str, Dict[str, Any]] = {}
        self._in_flight_ts: Dict[str, float] = {}
        self._dlq: List[Dict[str, Any]] = []

    async def enqueue(self, job: Dict[str, Any]) -> str:
        payload = dict(job)
        msg_id = payload.get("_message_id") or f"mem_{uuid.uuid4().hex[:12]}"
        payload["_message_id"] = msg_id
        await self._queue.put(payload)
        return msg_id

    async def dequeue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            msg_id = item.get("_message_id") or f"mem_{uuid.uuid4().hex[:12]}"
            item["_message_id"] = msg_id
            self._in_flight[msg_id] = dict(item)
            self._in_flight_ts[msg_id] = time.time()
            return item
        except asyncio.TimeoutError:
            return None

    async def ack(self, message_id: str) -> None:
        self._in_flight.pop(message_id, None)
        self._in_flight_ts.pop(message_id, None)

    async def reclaim_pending(self, min_idle_ms: int = 60000) -> List[Dict[str, Any]]:
        now = time.time()
        idle_threshold_s = min_idle_ms / 1000.0
        reclaimed = []
        for msg_id, start_ts in list(self._in_flight_ts.items()):
            if (now - start_ts) >= idle_threshold_s:
                item = self._in_flight.pop(msg_id, None)
                self._in_flight_ts.pop(msg_id, None)
                if item:
                    reclaimed.append(item)
                    await self._queue.put(item)
        return reclaimed

    def task_done(self) -> None:
        try:
            self._queue.task_done()
        except ValueError:
            pass

    async def enqueue_dlq(self, job: Dict[str, Any], reason: Optional[str] = None) -> None:
        dlq_entry = dict(job)
        if reason:
            dlq_entry["dlq_reason"] = reason
        dlq_entry["dlq_at"] = time.time()
        msg_id = dlq_entry.get("_message_id")
        if msg_id:
            await self.ack(msg_id)
        self._dlq.append(dlq_entry)

    async def get_depth(self) -> int:
        return self._queue.qsize() + len(self._in_flight)

    async def get_dlq_depth(self) -> int:
        return len(self._dlq)
