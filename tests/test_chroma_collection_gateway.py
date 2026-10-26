from __future__ import annotations

from src.retrieval.chroma_collection import ChromaCollectionGateway


class FakeCollection:
    def __init__(self) -> None:
        self.last_get: dict | None = None

    def get(self, **kwargs):
        self.last_get = kwargs
        return {"documents": ["第一条"], "metadatas": [{"article_id": "civil-1"}]}

    def count(self) -> int:
        return 1


class FakeVectorStore:
    def __init__(self) -> None:
        self._collection = FakeCollection()


def test_gateway_is_the_single_boundary_for_collection_reads() -> None:
    vectorstore = FakeVectorStore()
    gateway = ChromaCollectionGateway(vectorstore)

    payload = gateway.get(include=["documents", "metadatas"])

    assert payload["documents"] == ["第一条"]
    assert vectorstore._collection.last_get == {"include": ["documents", "metadatas"]}


def test_gateway_exposes_collection_count_without_leaking_the_collection() -> None:
    gateway = ChromaCollectionGateway(FakeVectorStore())

    assert gateway.count() == 1
