from unittest.mock import AsyncMock, MagicMock
from fastapi import Request
import pytest
from app.core.rate_limit import RateLimiter


def test_rate_limiter_sliding_window():
    """Verify that requests exceeding the configured limit are blocked with retry duration."""
    limiter = RateLimiter(requests_per_minute=3)
    key = "127.0.0.1:/api/v1/auth/login"

    # Requests 1, 2, 3 should succeed
    allowed1, retry1 = limiter.is_allowed(key)
    allowed2, retry2 = limiter.is_allowed(key)
    allowed3, retry3 = limiter.is_allowed(key)
    assert allowed1 is True
    assert allowed2 is True
    assert allowed3 is True

    # Request 4 should be rejected with 429 logic
    allowed4, retry4 = limiter.is_allowed(key)
    assert allowed4 is False
    assert retry4 > 0
    assert retry4 <= 60


def test_rate_limiter_distinct_keys():
    """Verify distinct IPs/endpoints have independent rate limits."""
    limiter = RateLimiter(requests_per_minute=2)
    key1 = "10.0.0.1:/api/v1/auth/login"
    key2 = "10.0.0.2:/api/v1/auth/login"

    assert limiter.is_allowed(key1)[0] is True
    assert limiter.is_allowed(key1)[0] is True
    assert limiter.is_allowed(key1)[0] is False  # key1 exhausted

    # key2 should still have quota
    assert limiter.is_allowed(key2)[0] is True
    assert limiter.is_allowed(key2)[0] is True
    assert limiter.is_allowed(key2)[0] is False


@pytest.mark.asyncio
async def test_rate_limiter_shared_redis_across_replicas():
    """Two separate RateLimiter instances sharing the same Redis client share quotas."""
    mock_redis = AsyncMock()
    # First call: 0 items in window -> allowed
    pipe1 = MagicMock()
    pipe1.execute = AsyncMock(return_value=[0, 0, []])
    pipe1_set = MagicMock()
    pipe1_set.execute = AsyncMock(return_value=[1, True])

    # Second call: 1 item in window (limit 1) -> blocked
    pipe2 = MagicMock()
    pipe2.execute = AsyncMock(return_value=[0, 1, [("now", 1700000000.0)]])

    mock_redis.pipeline = MagicMock(side_effect=[pipe1, pipe1_set, pipe2])

    replica1 = RateLimiter(requests_per_minute=1, redis_url="redis://fake:6379/0")
    replica1._redis = mock_redis

    replica2 = RateLimiter(requests_per_minute=1, redis_url="redis://fake:6379/0")
    replica2._redis = mock_redis

    key = "user_1:/api/v1/resource"
    allowed1, _ = await replica1.is_allowed_async(key)
    assert allowed1 is True

    # Replica 2 checks the shared quota and blocks the second request
    allowed2, retry2 = await replica2.is_allowed_async(key)
    assert allowed2 is False
    assert retry2 > 0


def test_client_ip_trusted_proxy():
    """Client IP extracts X-Forwarded-For only when peer host is in TRUSTED_PROXIES."""
    from app.core.rate_limit import get_client_ip
    from app.core.config import get_settings

    settings = get_settings()

    # Case 1: Untrusted proxy peer
    settings.TRUSTED_PROXIES = ["10.0.0.100"]
    req_untrusted = MagicMock(spec=Request)
    req_untrusted.client.host = "192.168.1.50"
    req_untrusted.headers = {"x-forwarded-for": "203.0.113.195"}
    assert get_client_ip(req_untrusted) == "192.168.1.50"

    # Case 2: Trusted proxy peer
    req_trusted = MagicMock(spec=Request)
    req_trusted.client.host = "10.0.0.100"
    req_trusted.headers = {"x-forwarded-for": "203.0.113.195, 10.0.0.100"}
    assert get_client_ip(req_trusted) == "203.0.113.195"
