"""查询期间可复用的只读检索运行时。"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any


class QueryRuntimeRegistry:
    """按 collection 缓存只读运行时，避免整条请求链使用全局串行锁。"""

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}
        self._chroma_clients: dict[str, Any] = {}
        self._lock = Lock()

    def get_or_create(self, collection_name: str, factory: Callable[[], Any]) -> Any:
        with self._lock:
            existing = self._items.get(collection_name)
            if existing is not None:
                return existing
            created = factory()
            self._items[collection_name] = created
            return created

    def invalidate(self, collection_name: str) -> None:
        with self._lock:
            self._items.pop(collection_name, None)

    def get_or_create_chroma_client(self, directory: str, factory: Callable[[], Any]) -> Any:
        """Reuse one embedded Chroma client per persistent directory."""
        with self._lock:
            existing = self._chroma_clients.get(directory)
            if existing is not None:
                return existing
            created = factory()
            self._chroma_clients[directory] = created
            return created
