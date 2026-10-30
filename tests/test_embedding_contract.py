"""Stage 3 contracts for explicit embedding and Chroma index identity."""

import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from config import Settings
from src.ingestion.index_identity import (
    EmbeddingIndexIdentity,
    IndexIdentityMismatchError,
    LegacyCollectionIdentityError,
    assert_collection_identity,
    get_or_create_identity_collection,
)
from src.utils.embedding_factory import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    EmbeddingInitializationError,
    ZhipuEmbeddings,
    clear_embedding_cache,
    create_embeddings,
)


@pytest.mark.parametrize(
    "metadata,error_type,error_code",
    [
        ({}, LegacyCollectionIdentityError, "INDEX_IDENTITY_LEGACY_REBUILD_REQUIRED"),
        (
            EmbeddingIndexIdentity("local", "BAAI/bge-m3", 768, True, 1).collection_metadata(),
            IndexIdentityMismatchError,
            "INDEX_IDENTITY_MISMATCH",
        ),
    ],
)
def test_collection_browse_rejects_legacy_or_mismatched_embedding_identity(
    monkeypatch, metadata, error_type, error_code
):
    """浏览路径也必须在读取 Chroma 文档之前验证 collection 身份。"""
    from app.services.knowledge_base_service import KnowledgeBaseService

    collection = SimpleNamespace(metadata=metadata)
    client = SimpleNamespace(get_collection=lambda _name: collection)
    fake_chromadb = ModuleType("chromadb")
    fake_chromadb.PersistentClient = lambda **_kwargs: client
    monkeypatch.setitem(sys.modules, "chromadb", fake_chromadb)

    with pytest.raises(error_type, match=error_code):
        KnowledgeBaseService._read_articles("kb_civil_code")

    assert not hasattr(collection, "get")


def test_embedding_factory_imports_without_ingestion_package_cycle():
    """Factory 是底层模块，直接导入也必须不触发循环依赖。"""
    root = Path(__file__).parent.parent
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from src.utils.embedding_factory import create_embeddings; print(create_embeddings.__name__)",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "create_embeddings"


def test_fingerprint_is_stable_and_changes_for_every_identity_field():
    """模型、provider、维度、归一化或格式变化绝不能复用 collection。"""
    baseline = EmbeddingIndexIdentity(
        provider="local",
        model="BAAI/bge-m3",
        dimensions=1024,
        normalize=True,
        schema_version=1,
    )

    assert baseline.fingerprint == EmbeddingIndexIdentity(
        provider="local",
        model="BAAI/bge-m3",
        dimensions=1024,
        normalize=True,
        schema_version=1,
    ).fingerprint
    for changed in (
        {"provider": "zhipu"},
        {"model": "embedding-3"},
        {"dimensions": 768},
        {"normalize": False},
        {"schema_version": 2},
    ):
        assert EmbeddingIndexIdentity(
            provider=changed.get("provider", baseline.provider),
            model=changed.get("model", baseline.model),
            dimensions=changed.get("dimensions", baseline.dimensions),
            normalize=changed.get("normalize", baseline.normalize),
            schema_version=changed.get("schema_version", baseline.schema_version),
        ).fingerprint != baseline.fingerprint


def test_settings_make_embedding_provider_and_index_format_explicit():
    settings = Settings()

    assert settings.embedding_provider == "local"
    assert settings.local_embedding_model_path == "/models/bge-m3"
    assert settings.local_embedding_model_id == "BAAI/bge-m3"
    assert settings.embedding_normalize is True
    assert settings.index_schema_version == 1


def test_all_vector_indexers_open_collections_through_identity_gate():
    root = Path(__file__).parent.parent
    for relative_path in (
        "src/ingestion/indexer.py",
        "src/ingestion/document_indexer.py",
        "src/ingestion/annual_case_indexer.py",
    ):
        assert "get_or_create_identity_collection" in (root / relative_path).read_text(
            encoding="utf-8"
        )


def test_document_indexer_persists_embedding_identity_metadata(monkeypatch, tmp_path):
    """首次写入的 collection 必须带身份；不是靠 collection 名猜测。"""
    from src.ingestion import document_indexer

    monkeypatch.setattr(document_indexer, "create_embeddings", lambda **_kwargs: object())
    monkeypatch.setattr(document_indexer.settings, "chroma_persist_directory", str(tmp_path))

    indexer = document_indexer.DocumentIndexer("identity_contract")

    metadata = indexer._vectorstore._collection.metadata
    assert metadata["lexrag_embedding_fingerprint"]
    assert metadata["lexrag_embedding_dimensions"] == 1024


def test_existing_collection_with_different_identity_is_rejected():
    expected = EmbeddingIndexIdentity("local", "BAAI/bge-m3", 1024, True, 1)
    incompatible = EmbeddingIndexIdentity("local", "BAAI/bge-m3", 768, True, 1)
    collection = SimpleNamespace(metadata=incompatible.collection_metadata())

    with pytest.raises(IndexIdentityMismatchError, match="INDEX_IDENTITY_MISMATCH"):
        assert_collection_identity(collection, expected)


def test_collection_without_identity_metadata_requires_explicit_rebuild():
    expected = EmbeddingIndexIdentity("local", "BAAI/bge-m3", 1024, True, 1)

    with pytest.raises(LegacyCollectionIdentityError, match="INDEX_IDENTITY_LEGACY_REBUILD_REQUIRED"):
        assert_collection_identity(SimpleNamespace(metadata={}), expected)


def test_new_collection_is_created_with_identity_metadata_and_existing_one_is_validated():
    identity = EmbeddingIndexIdentity("local", "BAAI/bge-m3", 1024, True, 1)

    class Client:
        def __init__(self):
            self.collection = None
            self.calls = []

        def get_or_create_collection(self, name, metadata):
            self.calls.append((name, metadata))
            if self.collection is None:
                self.collection = SimpleNamespace(metadata=metadata)
            return self.collection

    client = Client()
    first = get_or_create_identity_collection(client, "law_articles", identity)
    second = get_or_create_identity_collection(client, "law_articles", identity)

    assert first is second
    assert client.calls == [
        ("law_articles", identity.collection_metadata()),
        ("law_articles", identity.collection_metadata()),
    ]


def test_existing_collection_is_read_without_recreating_it():
    identity = EmbeddingIndexIdentity("local", "BAAI/bge-m3", 1024, True, 1)

    class Client:
        def __init__(self):
            self.collection = SimpleNamespace(metadata=identity.collection_metadata())
            self.created = False

        def get_collection(self, *, name):
            assert name == "law_articles"
            return self.collection

        def get_or_create_collection(self, *_args, **_kwargs):
            self.created = True
            raise AssertionError("must not recreate existing collection")

    client = Client()
    assert get_or_create_identity_collection(client, "law_articles", identity) is client.collection
    assert client.created is False


def test_local_provider_missing_directory_fails_without_zhipu_fallback(tmp_path):
    clear_embedding_cache()

    with pytest.raises(EmbeddingConfigurationError, match="EMBEDDING_LOCAL_MODEL_UNAVAILABLE") as error:
        create_embeddings(
            provider="local",
            model_path=str(tmp_path / "missing"),
            zhipuai_api_key="must-not-be-used",
            dimensions=1024,
        )

    assert "must-not-be-used" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_local_initialization_failure_does_not_fallback_to_zhipu(monkeypatch, tmp_path):
    """A selected local provider must never silently use a supplied remote key."""
    clear_embedding_cache()
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config_sentence_transformers.json").write_text("{}", encoding="utf-8")
    remote_key = "zhipu-key-must-not-appear"

    class FailingLocalEmbeddings:
        def __init__(self, **_kwargs):
            raise RuntimeError(f"local setup failed at {model_path}")

    class UnexpectedZhipuEmbeddings:
        def __init__(self, **_kwargs):
            raise AssertionError("ZhipuEmbeddings must not be invoked for local provider")

    monkeypatch.setitem(
        sys.modules,
        "langchain_community.embeddings",
        SimpleNamespace(HuggingFaceEmbeddings=FailingLocalEmbeddings),
    )
    monkeypatch.setattr(
        "src.utils.embedding_factory.ZhipuEmbeddings", UnexpectedZhipuEmbeddings
    )

    with pytest.raises(
        EmbeddingInitializationError,
        match="^EMBEDDING_LOCAL_INITIALIZATION_FAILED$",
    ) as error:
        create_embeddings(
            provider="local",
            model_path=str(model_path),
            zhipuai_api_key=remote_key,
        )

    assert remote_key not in str(error.value)
    assert str(model_path) not in str(error.value)


def test_zhipu_provider_requires_key_without_disclosing_it():
    clear_embedding_cache()

    with pytest.raises(EmbeddingConfigurationError, match="EMBEDDING_ZHIPU_API_KEY_MISSING"):
        create_embeddings(provider="zhipu", zhipuai_api_key=None)


def test_zhipu_embeddings_normalize_query_and_document_vectors(monkeypatch):
    """远端 provider 的 identity 声明 normalize=True 时，两个入口都必须真归一化。"""

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._body

    responses = iter(
        [
            {"data": [{"index": 0, "embedding": [3.0, 4.0]}]},
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 5.0]},
                    {"index": 0, "embedding": [3.0, 4.0]},
                ]
            },
        ]
    )

    def fake_urlopen(*_args, **_kwargs):
        return FakeResponse(json.dumps(next(responses)).encode("utf-8"))

    monkeypatch.setattr("src.utils.embedding_factory.urlopen", fake_urlopen)
    embeddings = ZhipuEmbeddings(api_key="test-key", model="embedding-3", normalize=True)

    assert embeddings.embed_query("查询") == [0.6, 0.8]
    assert embeddings.embed_documents(["文档一", "文档二"]) == [[0.6, 0.8], [0.0, 1.0]]


def test_zhipu_embeddings_preserve_vectors_when_normalization_is_disabled(monkeypatch):
    """identity 的 normalize=False 必须对应不改写远端向量。"""

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data": [{"index": 0, "embedding": [3.0, 4.0]}]}'

    monkeypatch.setattr("src.utils.embedding_factory.urlopen", lambda *_args, **_kwargs: FakeResponse())
    embeddings = ZhipuEmbeddings(api_key="test-key", model="embedding-3", normalize=False)

    assert embeddings.embed_query("查询") == [3.0, 4.0]


def test_factory_validates_actual_dimension_and_caches_by_fingerprint(monkeypatch, tmp_path):
    """不同 fingerprint 即使同一进程也必须创建不同实例。"""
    clear_embedding_cache()
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config_sentence_transformers.json").write_text("{}", encoding="utf-8")
    created = []

    class FakeEmbeddings:
        def __init__(self, **_kwargs):
            created.append(self)

        def embed_query(self, _text):
            return [0.0, 0.0]

    module = SimpleNamespace(HuggingFaceEmbeddings=FakeEmbeddings)
    monkeypatch.setitem(sys.modules, "langchain_community.embeddings", module)

    first = create_embeddings(
        provider="local", model_path=str(model_path), dimensions=2, normalize=True
    )
    same = create_embeddings(
        provider="local", model_path=str(model_path), dimensions=2, normalize=True
    )
    different = create_embeddings(
        provider="local", model_path=str(model_path), dimensions=2, normalize=False
    )

    assert first is same
    assert different is not first
    assert len(created) == 2


def test_factory_rejects_embedding_dimension_mismatch(monkeypatch, tmp_path):
    clear_embedding_cache()
    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config_sentence_transformers.json").write_text("{}", encoding="utf-8")

    class FakeEmbeddings:
        def __init__(self, **_kwargs):
            pass

        def embed_query(self, _text):
            return [0.0]

    monkeypatch.setitem(
        sys.modules,
        "langchain_community.embeddings",
        SimpleNamespace(HuggingFaceEmbeddings=FakeEmbeddings),
    )

    with pytest.raises(EmbeddingDimensionError, match="EMBEDDING_DIMENSION_MISMATCH"):
        create_embeddings(provider="local", model_path=str(model_path), dimensions=2)
