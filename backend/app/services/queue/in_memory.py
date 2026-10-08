import asyncio
from typing import Any, Dict, List, Optional
from app.services.queue.base import BaseQueueBackend


class InMemoryQueueBackend(BaseQueueBackend):
    """In-memory asyncio queue for local development and deterministic tests."""

    def __init__(self):
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._dlq: List[Dict[str, Any]] = []

    async def enqueue(self, job: Dict[str, Any]) -> None:
        await self._queue.put(job)

    async def dequeue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def task_done(self) -> None:
        try:
            self._queue.task_done()
        except ValueError:
            pass

    async def enqueue_dlq(self, job: Dict[str, Any]) -> None:
        self._dlq.append(job)

    async def get_depth(self) -> int:
        return self._queue.qsize()

    async def get_dlq_depth(self) -> int:
        return len(self._dlq)
