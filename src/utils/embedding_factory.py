"""Explicit, validated embedding providers with identity-scoped caching."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_embedding_instances: dict[str, object] = {}
_embedding_sources: dict[str, str] = {}


class EmbeddingConfigurationError(RuntimeError):
    """The explicitly selected provider lacks mandatory, non-secret configuration."""


class EmbeddingInitializationError(RuntimeError):
    """The selected provider failed; callers must not silently switch providers."""


class EmbeddingDimensionError(EmbeddingInitializationError):
    """The provider returned a vector incompatible with the configured collection."""


class ZhipuEmbeddings:
    """Small LangChain-compatible adapter that avoids the optional zhipuai SDK."""

    endpoint = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int | None = None,
        normalize: bool = True,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._normalize = normalize

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self._model, "input": texts}
        if self._dimensions is not None:
            payload["dimensions"] = self._dimensions
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS endpoint
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, ValueError) as error:
            logger.warning("Zhipu embedding request failed error_type=%s", type(error).__name__)
            raise EmbeddingInitializationError("EMBEDDING_ZHIPU_REQUEST_FAILED") from error
        try:
            items = sorted(body["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Zhipu embedding response invalid error_type=%s", type(error).__name__)
            raise EmbeddingInitializationError("EMBEDDING_ZHIPU_RESPONSE_INVALID") from error
        if not self._normalize:
            return vectors
        return [self._normalize_vector(vector) for vector in vectors]

    @staticmethod
    def _normalize_vector(vector: Any) -> list[float]:
        try:
            numeric_vector = [float(value) for value in vector]
            magnitude = math.sqrt(sum(value * value for value in numeric_vector))
        except (TypeError, ValueError) as error:
            logger.warning("Zhipu embedding vector invalid error_type=%s", type(error).__name__)
            raise EmbeddingInitializationError("EMBEDDING_ZHIPU_RESPONSE_INVALID") from error
        if magnitude == 0:
            logger.warning("Zhipu embedding returned a zero vector")
            raise EmbeddingInitializationError("EMBEDDING_ZHIPU_ZERO_VECTOR")
        return [value / magnitude for value in numeric_vector]


def create_embeddings(
    *,
    provider: str = "local",
    model_path: str = "/models/bge-m3",
    local_model_id: str = "BAAI/bge-m3",
    zhipuai_api_key: str | None = None,
    zhipuai_model: str = "embedding-3",
    dimensions: int = 1024,
    normalize: bool = True,
    index_schema_version: int = 1,
) -> object:
    """Build only the requested provider and verify its first vector's dimension.

    The returned instance is cached by the same identity that protects Chroma
    collections. Errors name stable codes/configuration keys and never expose a
    path or credential value.
    """
    # Import lazily: ``src.ingestion`` historically re-exports ``LawIndexer``,
    # which imports this factory.  Resolving the identity only when an embedding
    # is actually requested avoids a package-import cycle while keeping one
    # canonical fingerprint implementation.
    from src.ingestion.index_identity import EmbeddingIndexIdentity

    identity = EmbeddingIndexIdentity(
        provider=provider,
        model=local_model_id if provider == "local" else zhipuai_model,
        dimensions=dimensions,
        normalize=normalize,
        schema_version=index_schema_version,
    )
    cached = _embedding_instances.get(identity.fingerprint)
    if cached is not None:
        return cached

    if provider == "local":
        embeddings = _create_local_embeddings(model_path, normalize)
    elif provider == "zhipu":
        if not zhipuai_api_key:
            raise EmbeddingConfigurationError("EMBEDDING_ZHIPU_API_KEY_MISSING: zhipuai_api_key")
        embeddings = ZhipuEmbeddings(
            api_key=zhipuai_api_key,
            model=zhipuai_model,
            dimensions=dimensions,
            normalize=normalize,
        )
    else:
        raise EmbeddingConfigurationError("EMBEDDING_PROVIDER_INVALID: embedding_provider")

    _validate_dimension(embeddings, dimensions)
    _embedding_instances[identity.fingerprint] = embeddings
    _embedding_sources[identity.fingerprint] = f"{identity.provider}:{identity.model}"
    logger.info("Embedding loaded provider=%s model=%s", identity.provider, identity.model)
    return embeddings


def _create_local_embeddings(model_path: str, normalize: bool) -> object:
    path = Path(model_path)
    if not path.is_dir() or not (path / "config_sentence_transformers.json").is_file():
        raise EmbeddingConfigurationError("EMBEDDING_LOCAL_MODEL_UNAVAILABLE: local_embedding_model_path")
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(
            model_name=str(path),
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": normalize},
        )
    except Exception as error:
        logger.warning("Local embedding initialization failed error_type=%s", type(error).__name__)
        raise EmbeddingInitializationError("EMBEDDING_LOCAL_INITIALIZATION_FAILED") from error


def _validate_dimension(embeddings: Any, dimensions: int) -> None:
    try:
        vector = embeddings.embed_query("embedding health check")
    except EmbeddingInitializationError:
        raise
    except Exception as error:
        logger.warning("Embedding health check failed error_type=%s", type(error).__name__)
        raise EmbeddingInitializationError("EMBEDDING_PROVIDER_HEALTH_CHECK_FAILED") from error
    if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
        raise EmbeddingDimensionError("EMBEDDING_DIMENSION_MISMATCH: embedding_dimensions")


def get_embedding_source() -> str:
    """Return a safe source description without a local path or credentials."""
    if len(_embedding_sources) == 1:
        return next(iter(_embedding_sources.values()))
    return "unknown" if not _embedding_sources else "multiple"


def clear_embedding_cache() -> None:
    """Clear cached provider instances (used by tests and controlled reloads)."""
    _embedding_instances.clear()
    _embedding_sources.clear()
