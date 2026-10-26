"""Narrow adapter around LangChain Chroma's currently-private collection handle."""

from __future__ import annotations

from typing import Any


class ChromaCollectionGateway:
    """Centralize collection operations unavailable through LangChain's public API.

    Keeping this compatibility boundary small means a future move to the
    standalone Chroma integration changes one module rather than business code.
    """

    def __init__(self, vectorstore: Any) -> None:
        self._collection = vectorstore._collection

    def get(self, **kwargs: Any) -> dict[str, Any]:
        return self._collection.get(**kwargs)

    def count(self) -> int:
        return int(self._collection.count())
