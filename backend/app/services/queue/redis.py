import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional
import redis.asyncio as aioredis
from app.services.queue.base import BaseQueueBackend

logger = logging.getLogger("opspilot")


class RedisQueueBackend(BaseQueueBackend):
    """
    Production Redis-backed durable queue using Redis Streams.
    Guarantees crash-safety via consumer groups, explicit acknowledgement (XACK),
    PEL pending message reclamation (XAUTOCLAIM / XCLAIM), and persistent DLQ.
    """

    def __init__(
        self,
        redis_url: str,
        stream_name: str = "opspilot:stream:jobs",
        group_name: str = "opspilot:workers",
        consumer_name: Optional[str] = None,
        dlq_name: str = "opspilot:queue:dlq",
    ):
        self.redis_url = redis_url
        self.stream_name = stream_name
        self.queue_name = stream_name
        self.group_name = group_name
        self.consumer_name = consumer_name or f"worker_{uuid.uuid4().hex[:8]}"
        self.dlq_name = dlq_name
        self._client: Optional[aioredis.Redis] = None
        self._group_created: bool = False

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
        if not self._group_created:
            await self._ensure_consumer_group()
        return self._client

    async def _ensure_consumer_group(self) -> None:
        try:
            client = self._client
            if client is None:
                client = aioredis.from_url(self.redis_url, decode_responses=True)
                self._client = client
            await client.xgroup_create(self.stream_name, self.group_name, id="0", mkstream=True)
            self._group_created = True
        except Exception as exc:
            err_msg = str(exc)
            if "BUSYGROUP" in err_msg:
                self._group_created = True
            else:
                logger.warning(f"Could not create Redis stream consumer group {self.group_name}: {exc}")

    async def enqueue(self, job: Dict[str, Any]) -> str:
        client = await self._get_client()
        payload = json.dumps(job)
        msg_id = await client.xadd(self.stream_name, {"payload": payload})
        return str(msg_id)

    async def dequeue(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        block_ms = max(int(timeout * 1000), 100)
        try:
            entries = await client.xreadgroup(
                groupname=self.group_name,
                consumername=self.consumer_name,
                streams={self.stream_name: ">"},
                count=1,
                block=block_ms,
            )
            if not entries:
                return None
            for _stream, msgs in entries:
                if msgs:
                    msg_id, fields = msgs[0]
                    if "payload" in fields:
                        data = json.loads(fields["payload"])
                        data["_message_id"] = str(msg_id)
                        return data
        except Exception as e:
            logger.error(f"Error reading from Redis stream {self.stream_name}: {e}")
            return None
        return None

    async def ack(self, message_id: str) -> None:
        client = await self._get_client()
        try:
            await client.xack(self.stream_name, self.group_name, message_id)
        except Exception as e:
            logger.error(f"Failed to XACK message {message_id} on {self.stream_name}: {e}")

    async def reclaim_pending(self, min_idle_ms: int = 60000) -> List[Dict[str, Any]]:
        client = await self._get_client()
        reclaimed_jobs = []
        try:
            res = await client.xautoclaim(
                name=self.stream_name,
                groupname=self.group_name,
                consumername=self.consumer_name,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=10,
            )
            if len(res) >= 2 and res[1]:
                for msg_id, fields in res[1]:
                    if "payload" in fields:
                        data = json.loads(fields["payload"])
                        data["_message_id"] = str(msg_id)
                        reclaimed_jobs.append(data)
        except Exception:
            try:
                pending_info = await client.xpending_range(
                    name=self.stream_name,
                    groupname=self.group_name,
                    min="-",
                    max="+",
                    count=10,
                )
                for item in pending_info:
                    msg_id = item["message_id"]
                    idle_time = item["idle"]
                    if idle_time >= min_idle_ms:
                        claimed = await client.xclaim(
                            name=self.stream_name,
                            groupname=self.group_name,
                            consumername=self.consumer_name,
                            min_idle_time=min_idle_ms,
                            message_ids=[msg_id],
                        )
                        for c_id, fields in claimed:
                            if "payload" in fields:
                                data = json.loads(fields["payload"])
                                data["_message_id"] = str(c_id)
                                reclaimed_jobs.append(data)
            except Exception as claim_err:
                logger.error(f"Failed to reclaim pending stream messages: {claim_err}")
        return reclaimed_jobs

    def task_done(self) -> None:
        pass

    async def enqueue_dlq(self, job: Dict[str, Any], reason: Optional[str] = None) -> None:
        client = await self._get_client()
        dlq_entry = dict(job)
        if reason:
            dlq_entry["dlq_reason"] = reason
        dlq_entry["dlq_at"] = time.time()
        msg_id = dlq_entry.get("_message_id")
        if msg_id:
            await self.ack(msg_id)
        await client.rpush(self.dlq_name, json.dumps(dlq_entry))

    async def get_depth(self) -> int:
        client = await self._get_client()
        try:
            return await client.xlen(self.stream_name)
        except Exception:
            return 0

    async def get_dlq_depth(self) -> int:
        client = await self._get_client()
        try:
            return await client.llen(self.dlq_name)
        except Exception:
            return 0

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._group_created = False
