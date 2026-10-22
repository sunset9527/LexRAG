"""Deterministic process-local rate-limit contracts."""

import pytest


def test_fixed_window_limit_and_retry_after_are_deterministic():
    from app.security.rate_limit import ProcessRateLimiter, RateLimitExceeded

    limiter = ProcessRateLimiter(max_keys=10)
    limiter.check("login:127.0.0.1", limit=2, window_seconds=60, now=100)
    limiter.check("login:127.0.0.1", limit=2, window_seconds=60, now=110)

    with pytest.raises(RateLimitExceeded) as captured:
        limiter.check("login:127.0.0.1", limit=2, window_seconds=60, now=120)

    assert captured.value.retry_after_seconds == 40
    limiter.check("login:127.0.0.1", limit=2, window_seconds=60, now=161)


def test_limiter_bounds_its_in_memory_key_space():
    from app.security.rate_limit import ProcessRateLimiter

    limiter = ProcessRateLimiter(max_keys=2)
    limiter.check("old", limit=1, window_seconds=60, now=1)
    limiter.check("middle", limit=1, window_seconds=60, now=2)
    limiter.check("new", limit=1, window_seconds=60, now=3)

    assert limiter.key_count == 2
    assert "old" not in limiter.keys


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/auth/login", "auth"),
        ("POST", "/auth/register", "auth"),
        ("POST", "/query", "query"),
        ("POST", "/document-libraries/contracts/documents", "upload"),
        ("POST", "/documents/job-1/retry", "retry"),
        ("PUT", "/admin/agent-config", "admin_write"),
        ("GET", "/graph", None),
    ],
)
def test_sensitive_route_classification(method, path, expected):
    from app.security.rate_limit import classify_rate_limit

    assert classify_rate_limit(method, path) == expected
