"""Bounded process-local rate limiting for the current single-process deployment."""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitExceeded(RuntimeError):
    retry_after_seconds: int

    def __str__(self) -> str:
        return "请求过于频繁，请稍后重试"


class ProcessRateLimiter:
    """Sliding-window limiter with a bounded key set and injected clock support."""

    def __init__(self, *, max_keys: int = 10_000) -> None:
        self.max_keys = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("限流配置无效")
        moment = time.monotonic() if now is None else now
        threshold = moment - window_seconds
        with self._lock:
            events = self._events.pop(key, deque())
            while events and events[0] <= threshold:
                events.popleft()
            if len(events) >= limit:
                self._events[key] = events
                retry_after = max(1, math.ceil(events[0] + window_seconds - moment))
                raise RateLimitExceeded(retry_after)
            events.append(moment)
            self._events[key] = events
            while len(self._events) > self.max_keys:
                self._events.popitem(last=False)

    @property
    def key_count(self) -> int:
        return len(self._events)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._events)


def classify_rate_limit(method: str, path: str) -> str | None:
    method = method.upper()
    if method == "POST" and path in {"/auth/login", "/auth/register"}:
        return "auth"
    if method == "POST" and path == "/query":
        return "query"
    if method == "POST" and (
        path == "/upload"
        or (path.startswith("/document-libraries/") and path.endswith("/documents"))
        or path.endswith("/documents/batch")
        or path == "/scenarios/contract-file"
    ):
        return "upload"
    if method == "POST" and path.endswith("/retry"):
        return "retry"
    if method in {"POST", "PUT", "PATCH", "DELETE"} and (
        path.startswith("/admin")
        or path.startswith("/law-updates")
        or path.startswith("/prompts")
        or path.startswith("/knowledge-bases")
    ):
        return "admin_write"
    return None
