"""知识库注册表的业务服务。"""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from config import settings
from src.ingestion.chunker import StructuredLawChunker
from src.ingestion.index_identity import (
    IndexIdentityError,
    assert_collection_identity,
    collection_identity_from_settings,
)
from src.ingestion.indexer import LawIndexer
from src.ingestion.law_parser import LawParser

if TYPE_CHECKING:
    from src.ingestion.statute_catalog import StatuteIndexIdentity


class KnowledgeBaseAlreadyExistsError(ValueError):
    """创建时 slug 已被占用。"""


class KnowledgeBaseNotFoundError(ValueError):
    """操作的知识库不存在。"""


class KnowledgeBaseBusyError(ValueError):
    """知识库正在执行索引任务。"""


class KnowledgeBaseService:
    """封装知识库注册记录的创建和查询。"""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        parser: LawParser | None = None,
        chunker: StructuredLawChunker | None = None,
        indexer_factory: Callable[[str], LawIndexer] | None = None,
        article_reader: Callable[[str], list[dict[str, str]]] | None = None,
        collection_deleter: Callable[[str], None] | None = None,
    ):
        self._session_factory = session_factory
        self._parser = parser or LawParser()
        self._chunker = chunker or StructuredLawChunker(version="v1.9")
        self._indexer_factory = indexer_factory or self._create_indexer
        self._article_reader = article_reader or self._read_articles
        self._collection_deleter = collection_deleter or self._delete_collection

    def list_knowledge_bases(self) -> list[dict[str, Any]]:
        """按创建顺序返回所有知识库。"""
        with self._session_factory() as session:
            knowledge_bases = session.scalars(
                select(KnowledgeBase).order_by(KnowledgeBase.id)
            ).all()
            return [self._serialize(item) for item in knowledge_bases]

    def list_visible_knowledge_bases(self, *, organization_id: int) -> list[dict[str, Any]]:
        """列出当前组织自有库及明确标记为系统共享的库。"""
        with self._session_factory() as session:
            knowledge_bases = session.scalars(
                select(KnowledgeBase)
                .where(
                    or_(
                        KnowledgeBase.organization_id == organization_id,
                        KnowledgeBase.is_system_shared.is_(True),
                    )
                )
                .order_by(KnowledgeBase.id)
            ).all()
            return [self._serialize(item) for item in knowledge_bases]

    def create_knowledge_base(
        self,
        *,
        name: str,
        slug: str,
        law_area: str,
        organization_id: int | None = None,
        is_system_shared: bool = False,
    ) -> dict[str, Any]:
        """创建一个尚未索引的法规知识库。"""
        with self._session_factory() as session:
            existing = session.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == slug))
            if existing is not None:
                raise KnowledgeBaseAlreadyExistsError(f"知识库 slug 已存在: {slug}")

            knowledge_base = KnowledgeBase(
                name=name,
                slug=slug,
                type="statute",
                law_area=law_area,
                collection_name=self.collection_name_for_slug(slug),
                status="EMPTY",
                document_count=0,
                chunk_count=0,
                organization_id=organization_id,
                is_system_shared=is_system_shared,
            )
            session.add(knowledge_base)
            session.commit()
            session.refresh(knowledge_base)
            return self._serialize(knowledge_base)

    def create_document_library(
        self,
        *,
        name: str,
        slug: str,
        law_area: str,
        organization_id: int | None = None,
    ) -> dict[str, Any]:
        """创建一个尚未上传文档的自定义知识库。"""
        with self._session_factory() as session:
            existing = session.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == slug))
            if existing is not None:
                raise KnowledgeBaseAlreadyExistsError(f"知识库 slug 已存在: {slug}")

            knowledge_base = KnowledgeBase(
                name=name,
                slug=slug,
                type="document",
                law_area=law_area,
                collection_name=self.collection_name_for_slug(slug),
                status="EMPTY",
                document_count=0,
                chunk_count=0,
                organization_id=organization_id,
                is_system_shared=False,
            )
            session.add(knowledge_base)
            session.commit()
            session.refresh(knowledge_base)
            return self._serialize(knowledge_base)

    def rebuild_knowledge_base(self, slug: str, *, content: str) -> dict[str, Any]:
        """解析内容并仅重建指定知识库的专属 collection。"""
        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            if knowledge_base.status == "INDEXING":
                raise KnowledgeBaseBusyError(f"知识库正在重建: {slug}")
            previous_status = knowledge_base.status
            previous_error_message = knowledge_base.error_message
            knowledge_base.status = "INDEXING"
            knowledge_base.error_message = None
            session.commit()
            name = knowledge_base.name
            collection_name = knowledge_base.collection_name

        try:
            articles = self._parser.parse_law_content(content, name)
            chunks = self._chunker.chunk_articles(articles)
            indexed_count = self._indexer_factory(collection_name).rebuild_index(chunks)
        except IndexIdentityError:
            # A legacy or incompatible collection cannot be mutated safely by this
            # in-place route.  Preserve the last usable registry state so callers
            # can take an explicit, isolated migration path instead.
            with self._session_factory() as session:
                knowledge_base = self._get_by_slug(session, slug)
                knowledge_base.status = previous_status
                knowledge_base.error_message = previous_error_message
                session.commit()
            raise
        except Exception as exc:
            with self._session_factory() as session:
                knowledge_base = self._get_by_slug(session, slug)
                knowledge_base.status = "FAILED"
                knowledge_base.error_message = f"REBUILD_FAILED:{type(exc).__name__}"
                session.commit()
            raise

        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            knowledge_base.status = "READY"
            knowledge_base.document_count = len(articles)
            knowledge_base.chunk_count = indexed_count
            knowledge_base.last_indexed_at = datetime.now()
            knowledge_base.error_message = None
            session.commit()
            session.refresh(knowledge_base)
            return self._serialize(knowledge_base)

    def rebuild_confirmed_law_version(
        self, slug: str, *, organization_id: int, content: str, version_hash: str
    ) -> dict[str, Any]:
        """安全构建新法规版本：先写隔离 collection，全部成功后才原子切换指针。

        失败时绝不修改既有 READY collection 或其状态，确保当前查询仍可用。
        """
        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            if (
                knowledge_base.organization_id != organization_id
                or knowledge_base.type != "statute"
            ):
                raise KnowledgeBaseNotFoundError("知识库不存在或无访问权限")
            name = knowledge_base.name
            old_collection = knowledge_base.collection_name

        new_collection = f"{self.collection_name_for_slug(slug)}_v_{version_hash[:12]}"
        try:
            articles = self._parser.parse_law_content(content, name)
            chunks = self._chunker.chunk_articles(articles)
            indexed_count = self._indexer_factory(new_collection).rebuild_index(chunks)
        except Exception:
            # 最多留下未被引用的临时 collection；线上指针和 READY 状态保持不变。
            raise

        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            if knowledge_base.collection_name != old_collection:
                raise KnowledgeBaseBusyError("知识库版本已被其他确认操作切换，请重新检查")
            knowledge_base.collection_name = new_collection
            knowledge_base.status = "READY"
            knowledge_base.document_count = len(articles)
            knowledge_base.chunk_count = indexed_count
            knowledge_base.last_indexed_at = datetime.now()
            knowledge_base.error_message = None
            session.commit()
            session.refresh(knowledge_base)
            return self._serialize(knowledge_base)

    def rebuild_bootstrap_statute(
        self, slug: str, *, content: str, identity: "StatuteIndexIdentity"
    ) -> dict[str, Any]:
        """Build an isolated statute collection and atomically point the registry at it.

        The previous pointer is deliberately never opened, cleared or deleted.
        This makes a legacy ``law_articles`` collection harmless to bootstrap: it
        cannot be mistaken for a verified source/index identity.
        """
        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            expected_collection = identity.collection_name
            if (
                knowledge_base.status == "READY"
                and knowledge_base.collection_name == expected_collection
                and knowledge_base.source_hash == identity.source_hash
                and knowledge_base.embedding_fingerprint == identity.embedding_fingerprint
                and knowledge_base.index_schema_version == identity.index_schema_version
            ):
                result = self._serialize(knowledge_base)
                result["bootstrap_action"] = "skipped"
                return result
            if knowledge_base.status == "INDEXING":
                raise KnowledgeBaseBusyError(f"知识库正在重建: {slug}")
            old_collection = knowledge_base.collection_name
            name = knowledge_base.name

        articles = self._parser.parse_law_content(content, name)
        chunks = self._chunker.chunk_articles(articles)
        indexed_count = self._indexer_factory(expected_collection).rebuild_index(chunks)

        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            if knowledge_base.collection_name != old_collection:
                raise KnowledgeBaseBusyError("知识库版本已被其他 bootstrap 操作切换，请重新检查")
            knowledge_base.collection_name = expected_collection
            knowledge_base.status = "READY"
            knowledge_base.document_count = len(articles)
            knowledge_base.chunk_count = indexed_count
            knowledge_base.source_hash = identity.source_hash
            knowledge_base.embedding_fingerprint = identity.embedding_fingerprint
            knowledge_base.index_schema_version = identity.index_schema_version
            knowledge_base.last_indexed_at = datetime.now()
            knowledge_base.error_message = None
            session.commit()
            session.refresh(knowledge_base)
            result = self._serialize(knowledge_base)
            result["bootstrap_action"] = "rebuilt"
            return result

    def list_law_articles(
        self,
        slug: str,
        start_article: int | None = None,
        end_article: int | None = None,
    ) -> list[dict[str, str | int]]:
        """读取指定法规库中已索引的法条，用于法规浏览。"""
        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            collection_name = knowledge_base.collection_name
        articles = []
        for article in self._article_reader(collection_name):
            raw_article_number = str(article.get("article_number") or "")
            try:
                article_number = int(raw_article_number.split("-", maxsplit=1)[0])
            except ValueError:
                article_number = 0
            if start_article is not None and article_number < start_article:
                continue
            if end_article is not None and article_number > end_article:
                continue
            item = {
                "id": article.get("id") or article["article_id"],
                "content": article["content"],
            }
            if raw_article_number:
                item["article_number"] = (
                    article_number if raw_article_number.isdigit() else raw_article_number
                )
            articles.append(item)
        return articles

    def get_ready_collection_name(self, slug: str) -> str:
        """返回可供查询的 collection；未完成索引的库不可参与检索。"""
        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            if knowledge_base.status != "READY":
                raise ValueError(f"知识库不可用于检索，当前状态: {knowledge_base.status}")
            return knowledge_base.collection_name

    def get_ready_collection_name_for_organization(self, slug: str, *, organization_id: int) -> str:
        """只允许组织自有库或显式系统共享库参与检索。"""
        with self._session_factory() as session:
            knowledge_base = session.scalar(
                select(KnowledgeBase).where(
                    KnowledgeBase.slug == slug,
                    or_(
                        KnowledgeBase.organization_id == organization_id,
                        KnowledgeBase.is_system_shared.is_(True),
                    ),
                )
            )
            if knowledge_base is None:
                raise KnowledgeBaseNotFoundError("知识库不存在或无访问权限")
            if knowledge_base.status != "READY":
                raise ValueError(f"知识库不可用于检索，当前状态: {knowledge_base.status}")
            return knowledge_base.collection_name

    def get_visible_knowledge_base(
        self, slug: str, *, organization_id: int, require_owner: bool = False
    ) -> dict[str, Any]:
        """校验知识库对组织可见；写操作只能作用于组织自有库。"""
        with self._session_factory() as session:
            knowledge_base = session.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == slug))
            if knowledge_base is None:
                raise KnowledgeBaseNotFoundError("知识库不存在或无访问权限")
            if require_owner:
                is_allowed = knowledge_base.organization_id == organization_id
            else:
                is_allowed = (
                    knowledge_base.organization_id == organization_id
                    or knowledge_base.is_system_shared
                )
            if not is_allowed:
                raise KnowledgeBaseNotFoundError("知识库不存在或无访问权限")
            return self._serialize(knowledge_base)

    def delete_knowledge_base(self, slug: str) -> None:
        """删除一个非索引中的知识库及其专属 collection。"""
        with self._session_factory() as session:
            knowledge_base = self._get_by_slug(session, slug)
            if knowledge_base.status == "INDEXING":
                raise KnowledgeBaseBusyError(f"知识库正在重建: {slug}")
            collection_name = knowledge_base.collection_name

        self._collection_deleter(collection_name)
        with self._session_factory() as session:
            session.delete(self._get_by_slug(session, slug))
            session.commit()

    @staticmethod
    def collection_name_for_slug(slug: str) -> str:
        """将 URL 安全 slug 映射为独立 Chroma collection 名。"""
        return f"kb_{slug.replace('-', '_')}"

    @staticmethod
    def _create_indexer(collection_name: str) -> LawIndexer:
        return LawIndexer(
            persist_directory=settings.chroma_persist_directory,
            embedding_model=settings.embedding_model,
            collection_name=collection_name,
        )

    @staticmethod
    def _read_articles(collection_name: str) -> list[dict[str, str]]:
        """直接读取 Chroma collection，浏览场景无需加载 embedding 模型。"""
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        collection = client.get_collection(collection_name)
        assert_collection_identity(collection, collection_identity_from_settings(settings))
        data = collection.get(include=["documents", "metadatas"])
        articles: dict[str, dict[str, str]] = {}
        for content, metadata in zip(
            data.get("documents", []), data.get("metadatas", []), strict=True
        ):
            article_id = metadata.get("article_id", "")
            if article_id and article_id not in articles:
                articles[article_id] = {
                    "id": article_id,
                    "article_number": metadata.get("article_number", ""),
                    "content": content,
                }
        return list(articles.values())

    @staticmethod
    def _delete_collection(collection_name: str) -> None:
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        try:
            client.delete_collection(collection_name)
        except ValueError:
            # 空库可能还没有 collection；注册记录仍可安全删除。
            pass

    @staticmethod
    def _get_by_slug(session: Session, slug: str) -> KnowledgeBase:
        knowledge_base = session.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == slug))
        if knowledge_base is None:
            raise KnowledgeBaseNotFoundError(f"知识库不存在: {slug}")
        return knowledge_base

    @staticmethod
    def _serialize(knowledge_base: KnowledgeBase) -> dict[str, Any]:
        return {
            "id": knowledge_base.slug,
            "name": knowledge_base.name,
            "slug": knowledge_base.slug,
            "type": knowledge_base.type,
            "organization_id": knowledge_base.organization_id,
            "is_system_shared": knowledge_base.is_system_shared,
            "law_area": knowledge_base.law_area,
            "collection_name": knowledge_base.collection_name,
            "status": knowledge_base.status,
            "document_count": knowledge_base.document_count,
            "chunk_count": knowledge_base.chunk_count,
            "source_hash": knowledge_base.source_hash,
            "embedding_fingerprint": knowledge_base.embedding_fingerprint,
            "index_schema_version": knowledge_base.index_schema_version,
            "last_indexed_at": (
                knowledge_base.last_indexed_at.isoformat()
                if knowledge_base.last_indexed_at is not None
                else None
            ),
            "error_message": knowledge_base.error_message,
        }
