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
