"""Request IDs, stable error envelopes, and defensive log redaction."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.security.rate_limit import ProcessRateLimiter, RateLimitExceeded, classify_rate_limit
from config import settings

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_BEARER = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|password|jwt|token|authorization)[\"']?\s*[:=]\s*)"
    r"(?:[\"'][^\"']*[\"']|[^\s,;]+)"
)
_RATE_LIMITER = ProcessRateLimiter()


def normalize_request_id(value: str | None) -> str:
    """Return a safe caller ID or generate an opaque replacement."""

    if value and _REQUEST_ID.fullmatch(value):
        return value
    return uuid.uuid4().hex


def internal_error_payload(request_id: str, _error: Exception | None = None) -> dict[str, str]:
    """Build the only public representation of an unexpected server error."""

    return {
        "code": "INTERNAL_ERROR",
        "message": "服务暂时不可用，请稍后重试",
        "request_id": request_id,
    }


def redact_log_message(message: str) -> str:
    """Mask common credential shapes without attempting to log request bodies."""

    redacted = _BEARER.sub(r"\1[REDACTED]", str(message))
    return _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", redacted)


class SensitiveValueFilter(logging.Filter):
    """Defense-in-depth filter for messages emitted by third-party libraries."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        redacted = redact_log_message(rendered)
        if redacted != rendered:
            record.msg = redacted
            record.args = ()
        return True


class RequestSecurityMiddleware:
    """Raw ASGI middleware so unexpected errors cannot escape as plaintext."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app
        self.logger = logging.getLogger("lexrag.request")

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = request_headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = normalize_request_id(supplied)
        scope.setdefault("state", {})["request_id"] = request_id
        response_started = False

        async def secure_send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-request-id", request_id.encode("ascii")),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                )
                message["headers"] = headers
            await send(message)

        rate_class = classify_rate_limit(scope.get("method", ""), scope.get("path", ""))
        if rate_class:
            authorization = request_headers.get(b"authorization") or request_headers.get(b"cookie")
            if authorization:
                identity = hashlib.sha256(authorization).hexdigest()[:24]
            else:
                client = scope.get("client") or ("unknown", 0)
                identity = str(client[0])
            try:
                _RATE_LIMITER.check(
                    f"{rate_class}:{identity}",
                    limit=getattr(settings, f"rate_limit_{rate_class}"),
                    window_seconds=settings.rate_limit_window_seconds,
                )
            except RateLimitExceeded as exc:
                body = json.dumps(
                    {
                        "code": "RATE_LIMITED",
                        "message": str(exc),
                        "request_id": request_id,
                        "retry_after": exc.retry_after_seconds,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                await secure_send(
                    {
                        "type": "http.response.start",
                        "status": 429,
                        "headers": [
                            (b"content-type", b"application/json; charset=utf-8"),
                            (b"retry-after", str(exc.retry_after_seconds).encode("ascii")),
                        ],
                    }
                )
                await secure_send({"type": "http.response.body", "body": body})
                return

        try:
            await self.app(scope, receive, secure_send)
        except Exception as exc:
            self.logger.error(
                "Unhandled request failure request_id=%s method=%s path=%s error_type=%s",
                request_id,
                scope.get("method", ""),
                scope.get("path", ""),
                type(exc).__name__,
            )
            if response_started:
                raise
            body = json.dumps(
                internal_error_payload(request_id, exc), ensure_ascii=False
            ).encode("utf-8")
            await secure_send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"application/json; charset=utf-8")],
                }
            )
            await secure_send({"type": "http.response.body", "body": body})
