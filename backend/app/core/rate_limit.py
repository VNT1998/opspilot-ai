from collections import defaultdict
import time
from typing import Callable, Dict, List, Tuple
from fastapi import Request
from app.core.errors import RateLimitExceededError


class RateLimiter:
    """
    Sliding-window rate limiter.
    Enforces maximum request limits per 60-second window per client IP/resource key.
    """

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - 60.0
        # Evict timestamps outside current 60s sliding window
        self._history[key] = [t for t in self._history[key] if t > window_start]
        if len(self._history[key]) >= self.requests_per_minute:
            oldest = self._history[key][0]
            retry_after = max(int(60.0 - (now - oldest)), 1)
            return False, retry_after
        self._history[key].append(now)
        return True, 0

    def reset(self):
        self._history.clear()


def rate_limit(requests_per_minute: int = 60) -> Callable:
    """FastAPI dependency factory enforcing rate limits on endpoints."""
    limiter = RateLimiter(requests_per_minute=requests_per_minute)

    async def dependency(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        allowed, retry_after = limiter.is_allowed(key)
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit of {requests_per_minute} req/min exceeded. Please retry in {retry_after}s.",
                retry_after_seconds=retry_after,
            )
        return True

    return dependency
