from collections import defaultdict
import time
from typing import Callable, Dict, List, Optional, Tuple
from fastapi import Request
import redis.asyncio as aioredis
from app.core.errors import RateLimitExceededError


def get_client_ip(request: Request) -> str:
    """
    Extracts client IP. Respects X-Forwarded-For only when request comes from
    a configured trusted proxy (e.g. cloud reverse proxy or ingress).
    """
    from app.core.config import get_settings

    settings = get_settings()
    peer_ip = request.client.host if request.client else "unknown"

    if peer_ip in settings.TRUSTED_PROXIES or "127.0.0.1" in settings.TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                return client_ip
    return peer_ip


class RateLimiter:
    """
    Sliding-window rate limiter supporting shared Redis storage across replicas
    and an in-memory fallback with inactive key cleanup.
    """

    def __init__(self, requests_per_minute: int = 60, redis_url: Optional[str] = None):
        self.requests_per_minute = requests_per_minute
        self.redis_url = redis_url
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        from app.core.config import get_settings

        settings = get_settings()
        if settings.ENVIRONMENT == "production" or self.redis_url:
            url = self.redis_url or settings.REDIS_URL
            if self._redis is None and url:
                try:
                    self._redis = aioredis.from_url(url, decode_responses=True)
                except Exception:
                    self._redis = None
            return self._redis
        return None

    def _is_allowed_local(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - 60.0

        # Periodic cleanup of expired entries
        if len(self._history) > 500:
            for k in list(self._history.keys()):
                self._history[k] = [t for t in self._history[k] if t > window_start]
                if not self._history[k]:
                    del self._history[k]

        self._history[key] = [t for t in self._history[key] if t > window_start]
        if len(self._history[key]) >= self.requests_per_minute:
            oldest = self._history[key][0]
            retry_after = max(int(60.0 - (now - oldest)), 1)
            return False, retry_after
        self._history[key].append(now)
        return True, 0

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """Synchronous local check for deterministic tests and offline dev."""
        return self._is_allowed_local(key)

    async def is_allowed_async(self, key: str) -> Tuple[bool, int]:
        """
        Asynchronous check. Uses shared Redis ZSET sliding window in production,
        falling back to local memory if Redis is unavailable.
        """
        now = time.time()
        window_start = now - 60.0

        redis_client = await self._get_redis()
        if redis_client is not None:
            redis_key = f"opspilot:ratelimit:{key}"
            try:
                pipe = redis_client.pipeline(transaction=True)
                pipe.zremrangebyscore(redis_key, 0, window_start)
                pipe.zcard(redis_key)
                pipe.zrange(redis_key, 0, 0, withscores=True)
                _rem, count, oldest_items = await pipe.execute()

                if count >= self.requests_per_minute:
                    if oldest_items:
                        oldest_ts = float(oldest_items[0][1])
                        retry_after = max(int(60.0 - (now - oldest_ts)), 1)
                    else:
                        retry_after = 60
                    return False, retry_after

                pipe = redis_client.pipeline(transaction=True)
                pipe.zadd(redis_key, {str(now): now})
                pipe.expire(redis_key, 65)
                await pipe.execute()
                return True, 0
            except Exception:
                pass

        return self._is_allowed_local(key)

    def reset(self):
        self._history.clear()


def rate_limit(requests_per_minute: int = 60) -> Callable:
    """FastAPI dependency factory enforcing rate limits on endpoints."""
    limiter = RateLimiter(requests_per_minute=requests_per_minute)

    async def dependency(request: Request):
        client_ip = get_client_ip(request)
        key = f"{client_ip}:{request.url.path}"
        allowed, retry_after = await limiter.is_allowed_async(key)
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit of {requests_per_minute} req/min exceeded. Please retry in {retry_after}s.",
                retry_after_seconds=retry_after,
            )
        return True

    return dependency
