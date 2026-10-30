"""短生命周期查询事件存储的可测试边界。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_APPEND_EVENT_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
local sequence = redis.call('HINCRBY', KEYS[1], 'next_sequence', 1)
local event = cjson.decode(ARGV[1])
event['sequence'] = sequence
event['type'] = ARGV[2]
redis.call('RPUSH', KEYS[2], cjson.encode(event))
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[3]))
return sequence
"""


@dataclass(frozen=True)
class QueryEvent:
    sequence: int
    type: str
    data: dict[str, Any]


@dataclass
class _Run:
    user_id: int
    organization_id: int
    events: list[QueryEvent]
    cancel_requested: bool = False


class InMemoryQueryEventStore:
    """测试和单进程开发用的事件存储，不承担跨 Worker 分发。"""

    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}
        self._lock = Lock()

    def create_run(self, query_id: str, *, user_id: int, organization_id: int) -> None:
        with self._lock:
            self._runs[query_id] = _Run(
                user_id=user_id,
                organization_id=organization_id,
                events=[],
            )

    def append(self, query_id: str, event_type: str, data: dict[str, Any]) -> QueryEvent:
        with self._lock:
            run = self._runs[query_id]
            event = QueryEvent(sequence=len(run.events) + 1, type=event_type, data=dict(data))
            run.events.append(event)
            return event

    def events_after(self, query_id: str, *, after_sequence: int = 0) -> list[QueryEvent]:
        with self._lock:
            run = self._runs[query_id]
            return [event for event in run.events if event.sequence > after_sequence]

    def can_access(self, query_id: str, *, user_id: int, organization_id: int) -> bool:
        with self._lock:
            run = self._runs.get(query_id)
            return bool(
                run and run.user_id == user_id and run.organization_id == organization_id
            )

    def request_cancel(self, query_id: str) -> bool:
        with self._lock:
            run = self._runs[query_id]
            if run.cancel_requested:
                return False
            run.cancel_requested = True
            event = QueryEvent(sequence=len(run.events) + 1, type="cancelled", data={})
            run.events.append(event)
            return True

    def is_cancel_requested(self, query_id: str) -> bool:
        with self._lock:
            return self._runs[query_id].cancel_requested


class RedisQueryEventStore:
    """Redis 实现：事件和归属元数据短期保存，支持跨 Worker 回放。"""

    def __init__(self, redis_client: Any, *, ttl_seconds: int = 300) -> None:
        self._redis = redis_client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _meta_key(query_id: str) -> str:
        return f"lexrag:query-run:{query_id}:meta"

    @staticmethod
    def _events_key(query_id: str) -> str:
        return f"lexrag:query-run:{query_id}:events"

    def _refresh_ttl(self, query_id: str) -> None:
        self._redis.expire(self._meta_key(query_id), self._ttl_seconds)
        self._redis.expire(self._events_key(query_id), self._ttl_seconds)

    def create_run(self, query_id: str, *, user_id: int, organization_id: int) -> None:
        self._redis.hset(
            self._meta_key(query_id),
            mapping={
                "user_id": user_id,
                "organization_id": organization_id,
                "next_sequence": 0,
            },
        )
        self._refresh_ttl(query_id)

    def append(self, query_id: str, event_type: str, data: dict[str, Any]) -> QueryEvent:
        event_data = dict(data)
        sequence = int(
            self._redis.eval(
                _APPEND_EVENT_SCRIPT,
                2,
                self._meta_key(query_id),
                self._events_key(query_id),
                json.dumps({"data": event_data}, ensure_ascii=False, separators=(",", ":")),
                event_type,
                self._ttl_seconds,
            )
        )
        if sequence < 1:
            raise KeyError(f"查询运行不存在: {query_id}")
        return QueryEvent(sequence=sequence, type=event_type, data=event_data)

    def events_after(self, query_id: str, *, after_sequence: int = 0) -> list[QueryEvent]:
        raw_events = self._redis.lrange(self._events_key(query_id), 0, -1)
        events = []
        for raw in raw_events:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            event = QueryEvent(
                sequence=int(payload["sequence"]),
                type=str(payload["type"]),
                data=dict(payload.get("data") or {}),
            )
            if event.sequence > after_sequence:
                events.append(event)
        return events

    def can_access(self, query_id: str, *, user_id: int, organization_id: int) -> bool:
        metadata = self._redis.hgetall(self._meta_key(query_id)) or {}
        return (
            str(metadata.get("user_id")) == str(user_id)
            and str(metadata.get("organization_id")) == str(organization_id)
        )

    def request_cancel(self, query_id: str) -> bool:
        if not self._redis.hgetall(self._meta_key(query_id)):
            return False
        if not self._redis.hsetnx(self._meta_key(query_id), "cancel_requested", "1"):
            return False
        self.append(query_id, "cancelled", {})
        return True

    def is_cancel_requested(self, query_id: str) -> bool:
        metadata = self._redis.hgetall(self._meta_key(query_id)) or {}
        return str(metadata.get("cancel_requested")) == "1"


def create_query_event_store(redis_client: Any) -> RedisQueryEventStore | InMemoryQueryEventStore:
    """Return Redis-backed SSE storage, or the safe single-process fallback.

    ``Redis.from_url`` is lazy: constructing a client does not prove that a
    server is reachable.  Probe it here so local development can serve query
    runs without Redis instead of failing on the first ``create_run`` call.
    """

    try:
        if redis_client.ping() is not True:
            raise RuntimeError("REDIS_PING_FAILED")
    except Exception as exc:
        logger.warning("查询 Redis 不可用，SSE 已降级为单进程内存存储 error_type=%s", type(exc).__name__)
        return InMemoryQueryEventStore()
    return RedisQueryEventStore(redis_client)
