"""阶段 6 查询事件存储契约。"""

from __future__ import annotations

import json
from threading import Barrier, Event, Lock, Thread, local

from app.services import query_event_store
from app.services.query_event_store import InMemoryQueryEventStore, RedisQueryEventStore


def test_event_store_replays_only_events_after_the_requested_sequence():
    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)
    first = store.append("run-1", "accepted", {"session_id": "session-1"})
    second = store.append("run-1", "stage_completed", {"stage": "routing"})

    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.type for event in store.events_after("run-1", after_sequence=1)] == [
        "stage_completed"
    ]


def test_event_store_rejects_access_from_another_user_or_organization():
    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)

    assert store.can_access("run-1", user_id=7, organization_id=9)
    assert not store.can_access("run-1", user_id=8, organization_id=9)
    assert not store.can_access("run-1", user_id=7, organization_id=10)


def test_event_store_marks_a_run_cancelled_once_and_emits_the_terminal_event():
    store = InMemoryQueryEventStore()
    store.create_run("run-1", user_id=7, organization_id=9)

    assert store.request_cancel("run-1") is True
    assert store.request_cancel("run-1") is False
    assert store.is_cancel_requested("run-1") is True
    assert [event.type for event in store.events_after("run-1")] == ["cancelled"]


def test_event_store_factory_falls_back_to_in_memory_when_redis_is_unreachable():
    """本地单进程开发没有 Redis 时，SSE 查询仍应可受理。"""

    class UnreachableRedis:
        def ping(self):
            raise ConnectionError("connection refused")

    factory = getattr(query_event_store, "create_query_event_store", lambda _client: None)

    assert isinstance(factory(UnreachableRedis()), InMemoryQueryEventStore)


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.expirations = {}

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update({name: str(value) for name, value in mapping.items()})

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hincrby(self, key, name, amount):
        values = self.hashes.setdefault(key, {})
        values[name] = str(int(values.get(name, "0")) + amount)
        return int(values[name])

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lrange(self, key, _start, _end):
        return list(self.lists.get(key, []))

    def expire(self, key, seconds):
        self.expirations[key] = seconds

    def eval(self, _script, _key_count, *args):
        meta_key, events_key, raw_payload, event_type, ttl_seconds = args
        sequence = self.hincrby(meta_key, "next_sequence", 1)
        payload = json.loads(raw_payload)
        payload.update({"sequence": sequence, "type": event_type})
        self.rpush(events_key, json.dumps(payload, ensure_ascii=False))
        self.expire(meta_key, int(ttl_seconds))
        self.expire(events_key, int(ttl_seconds))
        return sequence


def test_redis_event_store_preserves_replay_and_sets_a_short_ttl():
    redis = FakeRedis()
    store = RedisQueryEventStore(redis, ttl_seconds=90)
    store.create_run("run-1", user_id=7, organization_id=9)
    store.append("run-1", "accepted", {"session_id": "session-1"})
    store.append("run-1", "completed", {"verification_status": "pass"})

    assert [event.sequence for event in store.events_after("run-1", after_sequence=1)] == [2]
    assert store.can_access("run-1", user_id=7, organization_id=9)
    assert redis.expirations["lexrag:query-run:run-1:meta"] == 90
    assert redis.expirations["lexrag:query-run:run-1:events"] == 90


class RacingCancelRedis(FakeRedis):
    """让两个旧式“读后写”取消请求稳定地发生竞争。"""

    def __init__(self):
        super().__init__()
        self.cancel_reads = Barrier(2)
        self.lock = Lock()

    def hgetall(self, key):
        payload = super().hgetall(key)
        self.cancel_reads.wait(timeout=1)
        return payload

    def hsetnx(self, key, name, value):
        with self.lock:
            values = self.hashes.setdefault(key, {})
            if name in values:
                return 0
            values[name] = str(value)
            return 1


def test_redis_event_store_cancels_a_concurrent_run_exactly_once():
    redis = RacingCancelRedis()
    store = RedisQueryEventStore(redis)
    store.create_run("run-1", user_id=7, organization_id=9)
    results = []

    def cancel():
        results.append(store.request_cancel("run-1"))

    first = Thread(target=cancel)
    second = Thread(target=cancel)
    first.start()
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)

    assert sorted(results) == [False, True]
    assert [event.type for event in store.events_after("run-1")] == ["cancelled"]


class RacingAppendRedis(FakeRedis):
    """模拟旧式“自增后另行写列表”可能让较大序号先进入列表。"""

    def __init__(self):
        super().__init__()
        self._thread_state = local()
        self.sequence_ready = Barrier(2)
        self.sequence_two_pushed = Event()
        self.lock = Lock()

    def hincrby(self, key, name, amount):
        with self.lock:
            sequence = super().hincrby(key, name, amount)
        self._thread_state.sequence = sequence
        self.sequence_ready.wait(timeout=1)
        return sequence

    def rpush(self, key, value):
        if self._thread_state.sequence == 1:
            self.sequence_two_pushed.wait(timeout=1)
        else:
            self.sequence_two_pushed.set()
        return super().rpush(key, value)

    def eval(self, _script, _key_count, *args):
        meta_key, events_key, raw_payload, event_type, ttl_seconds = args
        with self.lock:
            sequence = super().hincrby(meta_key, "next_sequence", 1)
            payload = json.loads(raw_payload)
            payload.update({"sequence": sequence, "type": event_type})
            super().rpush(events_key, json.dumps(payload, ensure_ascii=False))
            super().expire(meta_key, int(ttl_seconds))
            super().expire(events_key, int(ttl_seconds))
        return sequence


def test_redis_event_store_replays_concurrent_events_in_sequence_order():
    redis = RacingAppendRedis()
    store = RedisQueryEventStore(redis)
    store.create_run("run-1", user_id=7, organization_id=9)

    first = Thread(target=lambda: store.append("run-1", "stage_completed", {"stage": "a"}))
    second = Thread(target=lambda: store.append("run-1", "stage_completed", {"stage": "b"}))
    first.start()
    second.start()
    first.join(timeout=2)
    second.join(timeout=2)

    assert [event.sequence for event in store.events_after("run-1")] == [1, 2]
