import json
import logging
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
from app.services.queue.base import BaseQueueBackend

logger = logging.getLogger("opspilot")


class RedisQueueBackend(BaseQueueBackend):
    """Production Redis-backed durable queue with DLQ and persistence."""

    def __init__(self, redis_url: str, queue_name: str = "opspilot:jobs", dlq_name: str = "opspilot:dlq"):
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.dlq_name = dlq_name
        self._client: Optional[aioredis.Redis] = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def enqueue(self, job: Dict[str, Any]) -> None:
        client = await self._get_client()
        await client.rpush(self.queue_name, json.dumps(job))

    async def dequeue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        item = await client.blpop(self.queue_name, timeout=int(max(timeout, 1)))
        if item:
            _, payload = item
            return json.loads(payload)
        return None

    def task_done(self) -> None:
        # Redis BLPOP is atomic and needs no local task_done
        pass

    async def enqueue_dlq(self, job: Dict[str, Any]) -> None:
        client = await self._get_client()
        await client.rpush(self.dlq_name, json.dumps(job))

    async def get_depth(self) -> int:
        client = await self._get_client()
        return await client.llen(self.queue_name)

    async def get_dlq_depth(self) -> int:
        client = await self._get_client()
        return await client.llen(self.dlq_name)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
