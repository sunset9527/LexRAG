"""Runtime bridge between HTTP query routes and query orchestration."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryRouteService:
    get_event_store: Callable[[], Any]
    execute_query_run: Callable[..., Awaitable[None]]
    execute_query: Callable[..., Awaitable[Any]]
    iterate_events: Callable[..., AsyncIterator[str]]
