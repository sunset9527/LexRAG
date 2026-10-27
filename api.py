"""
FastAPI 后端服务 — LexRAG API

提供 RESTful API 接口
当前应用口径：v3.0 收口期
历史说明：v1.7 引入认证系统、Prompt 管理、数据库和 Langfuse 可观测性
"""

# ⚠️ HF_ENDPOINT 必须在所有 import 之前设置，否则 sentence_transformers 会直连 huggingface.co
import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import asyncio
import hashlib
import logging
import time
import uuid
from contextlib import asynccontextmanager, nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
)
from fastapi.responses import StreamingResponse

from app.api.admin import (
    get_authorization_context,
)
from app.api.auth import get_current_user
from app.api.knowledge_bases import (
    require_knowledge_base_access as _require_runtime_knowledge_base_access,
)
from app.db import session as db_session

# v1.7 历史增量：认证、数据库与平台服务模块
from app.db.session import init_db
from app.main import create_application
from app.models.user import User
from app.runtime import RuntimeContainer
from app.schemas.knowledge_bases import UploadRequest as UploadRequest  # noqa: F401
from app.schemas.query import QueryRequest, QueryResponse, QueryRunAccepted
from app.security.request_security import SensitiveValueFilter
from app.security.runtime_llm import RuntimeLLMPolicy
from app.services import query_execution_service
from app.services.audit_service import AuditService
from app.services.authorization_service import AuthorizationContext
from app.services.case_ingestion_service import CaseIngestionService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_result_service import DocumentResultService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.langfuse_helper import create_llm, flush_langfuse
from app.services.metrics import record_query_metrics
from app.services.query_cache_service import QueryCacheService
from app.services.query_event_store import QueryEvent, RedisQueryEventStore
from app.services.query_route_service import QueryRouteService
from app.services.query_run_service import QueryRunService
from app.services.query_runtime_registry import QueryRuntimeRegistry
from app.services.query_version_service import QueryVersionService
from app.services.readiness_probes import (
    RuntimeReadinessDependencies,
    alembic_head_revision,
    build_runtime_checks,
    check_persisted_law_graph,
)
from app.services.readiness_service import ReadinessService
from app.services.session_service import ConversationTurn, SessionNotFoundError, SessionService
from app.services.statute_version_chain_service import StatuteVersionChainService
from app.services.usage_service import UsageService
from app.tasks.document_tasks import process_document_task
from config import get_project_root, settings, validate_security_settings
from src.graph.law_graph import LawGraph
from src.ingestion.annual_case_indexer import AnnualCaseIndexer
from src.ingestion.case_ocr import count_pdf_pages
from src.ingestion.index_identity import (
    collection_identity_from_settings,
    get_or_create_identity_collection,
)
from src.ingestion.indexer import LawIndexer
from src.ingestion.statute_catalog import STATUTE_CATALOG, StatuteIndexIdentity
from src.retrieval.annual_case_retriever import AnnualCaseRetriever
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.case_retriever import CaseRetriever
from src.retrieval.chroma_collection import ChromaCollectionGateway
from src.retrieval.context_compressor import ContextCompressor
from src.retrieval.graph_retriever import GraphRetriever
from src.retrieval.intent_router import IntentRouter
from src.retrieval.knowledge_base_router import KnowledgeBaseRouter
from src.retrieval.law_retriever import LawRetriever
from src.retrieval.multi_knowledge_base_retriever import MultiKnowledgeBaseLawRetriever
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.reranker import CrossEncoderReranker
from src.utils.embedding_factory import create_embeddings
from src.workflow.legal_evidence_workflow import (
    LegalEvidenceWorkflow,
    QueryCancelled,
    QueryEnhancedLawRetriever,
    RouteDecision,
)

# 配置日志
logging.basicConfig(level=getattr(logging, settings.log_level), format=settings.log_format)
logger = logging.getLogger(__name__)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(SensitiveValueFilter())
runtime_llm_policy = RuntimeLLMPolicy(settings)


def _append_audit_event(
    http_request: Request,
    context: AuthorizationContext,
    *,
    action: str,
    target_type: str,
    target_id: str | None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort append-only audit for sensitive mutations, without payloads."""

    service = components.get("audit_service")
    if service is None:
        return
    request_id = getattr(http_request.state, "request_id", None)
    seed = f"{request_id or uuid.uuid4().hex}:{action}:{target_type}:{target_id or ''}"
    try:
        service.append_event(
            event_id=hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            status=status,
            request_id=request_id,
            metadata=metadata,
        )
    except Exception as exc:
        logger.error(
            "审计写入失败 request_id=%s action=%s error_type=%s",
            request_id,
            action,
            type(exc).__name__,
        )


# ==================== 数据模型 ====================


def _require_knowledge_base_access(
    slug: str, context: AuthorizationContext, *, manage: bool = False
) -> None:
    """文档端点复用知识库路由的组织级访问控制。"""

    _require_runtime_knowledge_base_access(slug, context, components, manage=manage)


# ==================== 全局组件 ====================

components = RuntimeContainer()


def is_cacheable_query_result(payload: dict[str, Any]) -> bool:
    return query_execution_service.is_cacheable_query_result(payload)


def record_query_observability(
    *,
    event_id: str,
    organization_id: int,
    current_user_id: int,
    question: str,
    answer: str,
    verification_status: str,
    metadata: dict[str, Any],
    latency_ms: int,
) -> None:
    query_execution_service.record_query_observability(
        event_id=event_id,
        organization_id=organization_id,
        current_user_id=current_user_id,
        question=question,
        answer=answer,
        verification_status=verification_status,
        metadata=metadata,
        latency_ms=latency_ms,
        audit_service=components.get("audit_service"),
        usage_service=components.get("usage_service"),
        metrics_recorder=record_query_metrics,
    )


def build_evidence_answer_generator(
    llm,
    *,
    memory_turns: list[ConversationTurn] | None = None,
    repair_llm=None,
):
    return query_execution_service.build_evidence_answer_generator(
        llm,
        memory_turns=memory_turns,
        repair_llm=repair_llm,
    )


def build_evidence_planner(llm):
    return query_execution_service.build_evidence_planner(llm)


def build_runtime_operation_llms(
    *, api_key: str | None, base_url: str, model: str
) -> dict[str, Any]:
    """Create separately bounded LLM clients for one query's workflow stages."""

    common = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": 0.1,
    }
    return {
        "answer": create_llm(
            **common,
            request_timeout=settings.runtime_llm_answer_timeout_seconds,
            max_retries=settings.runtime_llm_answer_max_retries,
        ),
        "planning": create_llm(
            **common,
            request_timeout=settings.runtime_llm_planning_timeout_seconds,
            max_retries=settings.runtime_llm_planning_max_retries,
        ),
        "repair": create_llm(
            **common,
            request_timeout=settings.runtime_llm_repair_timeout_seconds,
            max_retries=settings.runtime_llm_repair_max_retries,
        ),
    }


def route_evidence_workflow(question: str) -> RouteDecision:
    return query_execution_service.route_evidence_workflow(question)


def initialize_components():
    """初始化组件"""
    try:
        knowledge_base_service = None
        document_ingestion_service = None
        document_result_service = None
        case_ingestion_service = None
        annual_case_retriever = None
        query_cache_service = None
        query_event_store = None
        query_version_service = None
        try:
            import redis

            redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            query_cache_service = QueryCacheService(
                redis_client,
                ttl_seconds=settings.query_cache_ttl_seconds,
                semantic_threshold=settings.query_cache_semantic_threshold,
            )
            query_event_store = RedisQueryEventStore(redis_client)
        except Exception as exc:
            logger.warning("查询 Redis 服务初始化失败 error_type=%s", type(exc).__name__)
        if db_session.SessionLocal is not None:
            knowledge_base_service = KnowledgeBaseService(db_session.SessionLocal)
            query_version_service = QueryVersionService(
                StatuteVersionChainService(db_session.SessionLocal), knowledge_base_service
            )
            document_ingestion_service = DocumentIngestionService(
                db_session.SessionLocal,
                uploads_root=Path(settings.document_uploads_path),
                task_dispatcher=lambda job_id: process_document_task.delay(job_id),
            )
            document_result_service = DocumentResultService(db_session.SessionLocal)
            case_ingestion_service = CaseIngestionService(
                db_session.SessionLocal,
                page_counter=count_pdf_pages,
            )
            try:
                annual_case_indexer = AnnualCaseIndexer()
                annual_case_retriever = AnnualCaseRetriever(
                    annual_case_indexer.vectorstore,
                    case_loader=case_ingestion_service.get_case,
                )
            except Exception as exc:
                logger.warning("年度案例检索器初始化失败 error_type=%s", type(exc).__name__)

        # 初始化意图路由器
        intent_router = IntentRouter(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )

        # 法条检索器必须按请求所选知识库的活动 collection 构造。
        # 启动期绝不创建或打开历史默认 ``law_articles`` collection。
        law_indexer = None
        law_retriever = None

        # 判例检索器
        case_retriever = None
        try:
            from langchain_community.vectorstores import Chroma

            case_db_path = Path(settings.chroma_persist_directory) / "cases"
            if law_retriever is not None and case_db_path.exists():
                case_embeddings = create_embeddings(
                    provider=settings.embedding_provider,
                    model_path=settings.local_embedding_model_path,
                    local_model_id=settings.local_embedding_model_id,
                    zhipuai_api_key=settings.zhipuai_api_key,
                    zhipuai_model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                    normalize=settings.embedding_normalize,
                    index_schema_version=settings.index_schema_version,
                )
                from chromadb import PersistentClient

                case_client = PersistentClient(path=str(case_db_path))
                case_identity = collection_identity_from_settings(settings)
                get_or_create_identity_collection(
                    case_client, settings.case_collection_name, case_identity
                )
                case_vectorstore = Chroma(
                    collection_name=settings.case_collection_name,
                    embedding_function=case_embeddings,
                    persist_directory=str(case_db_path),
                    client=case_client,
                    collection_metadata=case_identity.collection_metadata(),
                )
                case_retriever = CaseRetriever(
                    case_vectorstore=case_vectorstore,
                    law_retriever=law_retriever,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model,
                )
                logger.info("判例检索器初始化成功")
            else:
                logger.info("判例数据库不存在，跳过判例检索器初始化")
        except Exception as exc:
            logger.warning("判例检索器初始化失败 error_type=%s", type(exc).__name__)

        # BM25检索器
        bm25_retriever = None
        if settings.bm25_enabled and law_indexer is not None:
            try:
                bm25_retriever = BM25Retriever()
                # 从ChromaDB加载文档构建索引
                try:
                    all_data = ChromaCollectionGateway(law_indexer.vectorstore).get(
                        include=["documents", "metadatas"]
                    )
                    if all_data and all_data.get("documents"):
                        bm25_docs = []
                        for i, doc_content in enumerate(all_data["documents"]):
                            meta = all_data["metadatas"][i] if all_data.get("metadatas") else {}
                            bm25_docs.append(
                                {
                                    "doc_id": meta.get("article_id", f"doc_{i}"),
                                    "content": doc_content,
                                    "metadata": meta,
                                }
                            )
                        bm25_retriever.build_index(bm25_docs)
                except Exception as exc:
                    logger.warning("BM25索引构建失败 error_type=%s", type(exc).__name__)
                    bm25_retriever = None
            except Exception as exc:
                logger.warning("BM25初始化失败 error_type=%s", type(exc).__name__)

        # Reranker
        reranker = None
        if settings.reranker_enabled:
            try:
                reranker = CrossEncoderReranker(model_name=settings.reranker_model)
            except Exception as exc:
                logger.warning("Reranker初始化失败 error_type=%s", type(exc).__name__)

        # Query Rewriter
        query_rewriter = None
        if settings.query_rewriting_enabled:
            try:
                query_rewriter = QueryRewriter(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model,
                    request_timeout=settings.runtime_llm_query_rewrite_timeout_seconds,
                    max_retries=settings.runtime_llm_query_rewrite_max_retries,
                )
            except Exception as exc:
                logger.warning("Query Rewriter初始化失败 error_type=%s", type(exc).__name__)

        # Context Compressor
        _context_compressor = None
        if settings.context_compress_enabled:
            try:
                _context_compressor = ContextCompressor(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model,
                )
            except Exception as exc:
                logger.warning("Context Compressor初始化失败 error_type=%s", type(exc).__name__)

        # 初始化知识图谱
        law_graph_path = get_project_root() / settings.law_graph_path
        if law_graph_path.exists():
            law_graph = LawGraph.from_json(str(law_graph_path))
        else:
            law_graph = LawGraph()

        # v3.0 的 LangGraph 工作流门面按请求装配依赖，以支持知识库和运行时模型配置。
        # 此处只保留就绪标记供健康检查和已有 API 契约使用，不保存请求状态或密钥。
        workflow = "evidence-v3.0"
        graph_retriever = GraphRetriever(law_graph.graph)

        components.replace(
            **{
                "workflow": workflow,
                "law_indexer": law_indexer,
                "law_graph": law_graph,
                "intent_router": intent_router,
                "law_retriever": law_retriever,
                "case_retriever": case_retriever,
                "bm25_retriever": bm25_retriever,
                "reranker": reranker,
                "query_rewriter": query_rewriter,
                "graph_retriever": graph_retriever,
                "knowledge_base_service": knowledge_base_service,
                "query_version_service": query_version_service,
                "document_ingestion_service": document_ingestion_service,
                "document_result_service": document_result_service,
                "case_ingestion_service": case_ingestion_service,
                "annual_case_retriever": annual_case_retriever,
                "query_cache_service": query_cache_service,
                "query_event_store": query_event_store,
                "query_runtime_registry": QueryRuntimeRegistry(),
            }
        )

        def check_graph() -> None:
            check_persisted_law_graph(law_graph_path)
            if components.get("graph_retriever") is None:
                raise RuntimeError("GRAPH_RETRIEVER_UNAVAILABLE")
            if law_graph.graph.number_of_nodes() == 0:
                raise RuntimeError("RUNTIME_GRAPH_EMPTY")
            law_graph.get_statistics()

        def check_statutes() -> None:
            if knowledge_base_service is None:
                raise RuntimeError("STATUTE_REGISTRY_UNAVAILABLE")
            embedding_identity = collection_identity_from_settings(settings)
            identities = {
                item.definition.slug: StatuteIndexIdentity(
                    slug=item.definition.slug,
                    source_hash=item.clean_text_sha256,
                    embedding_fingerprint=embedding_identity.fingerprint,
                    index_schema_version=embedding_identity.schema_version,
                )
                for item in STATUTE_CATALOG
            }
            knowledge_base_service.assert_system_shared_statutes_ready(identities)

        def load_embedding() -> object:
            return create_embeddings(
                provider=settings.embedding_provider,
                model_path=settings.local_embedding_model_path,
                local_model_id=settings.local_embedding_model_id,
                zhipuai_api_key=settings.zhipuai_api_key,
                zhipuai_model=settings.embedding_model,
                dimensions=settings.embedding_dimensions,
                normalize=settings.embedding_normalize,
                index_schema_version=settings.index_schema_version,
            )

        def create_redis_client(redis_url: str) -> object:
            import redis

            return redis.Redis.from_url(redis_url, decode_responses=True)

        readiness_timeouts = {
            "database": settings.readiness_database_timeout_seconds,
            "migration": settings.readiness_migration_timeout_seconds,
            "redis": settings.readiness_redis_timeout_seconds,
            "embedding": settings.readiness_embedding_timeout_seconds,
            "graph": settings.readiness_graph_timeout_seconds,
            "statutes": settings.readiness_statutes_timeout_seconds,
        }
        components["readiness_service"] = ReadinessService(
            build_runtime_checks(
                RuntimeReadinessDependencies(
                    session_factory=db_session.SessionLocal,
                    alembic_head=lambda: alembic_head_revision(get_project_root()),
                    redis_client_factory=create_redis_client,
                    redis_url=settings.redis_url,
                    embedding_loader=load_embedding,
                    graph_checker=check_graph,
                    statute_checker=check_statutes,
                    timeouts=readiness_timeouts,
                )
            )
        )

        logger.info("组件初始化完成")
        return True

    except Exception as exc:
        logger.error("组件初始化失败 error_type=%s", type(exc).__name__)
        return False


# ==================== 生命周期管理 ====================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    validate_security_settings(settings)
    logger.info("启动 LexRAG 应用...")

    # v1.7: 设置 HuggingFace 镜像（国内加速）
    import os

    if settings.hf_endpoint and not os.environ.get("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = settings.hf_endpoint
        logger.info(f"HuggingFace 镜像已设置: {settings.hf_endpoint}")

    # v1.7: 初始化数据库
    try:
        init_db()
        if db_session.SessionLocal is not None:
            components.register("audit_service", AuditService(db_session.SessionLocal))
            components.register("usage_service", UsageService(db_session.SessionLocal))
        logger.info("数据库已就绪")
    except Exception as exc:
        logger.error("数据库初始化失败 error_type=%s", type(exc).__name__)

    # 初始化检索组件
    initialize_components()
    register_query_route_service()
    app.state.runtime = components

    # 打印 Embedding 来源
    from src.utils.embedding_factory import get_embedding_source

    logger.info(f"Embedding 来源: {get_embedding_source()}")

    yield

    # v1.7: 刷新 Langfuse 缓冲区
    flush_langfuse()
    logger.info("LexRAG 应用已关闭")


# ==================== 创建应用 ====================

app = create_application(lifespan=lifespan)
app.state.runtime = components


# ==================== API端点 ====================


def _query_event_store() -> Any:
    store = components.get("query_event_store")
    if store is None:
        raise HTTPException(status_code=503, detail="查询事件服务未初始化")
    return store


def _query_run_service() -> QueryRunService:
    return QueryRunService(run_query=lambda **kwargs: query(**kwargs))


def _invalidate_rebuilt_collection_runtime(result: dict[str, Any]) -> None:
    """丢弃刚被原地重建的 collection 的只读检索器缓存。"""
    collection_name = result.get("collection_name")
    registry = components.get("query_runtime_registry")
    if isinstance(collection_name, str) and collection_name and registry is not None:
        registry.invalidate(collection_name)


def _sse_encode(event: QueryEvent) -> str:
    return _query_run_service().encode_event(event)


async def iter_query_run_events(
    *,
    store: Any,
    query_id: str,
    after_sequence: int,
    is_disconnected: Any,
):
    """Backward-compatible wrapper for the query-run service iterator."""
    async for event in _query_run_service().iter_events(
        store=store,
        query_id=query_id,
        after_sequence=after_sequence,
        is_disconnected=is_disconnected,
    ):
        yield event


async def invoke_workflow_in_worker(
    workflow: LegalEvidenceWorkflow,
    question: str,
    **kwargs: Any,
) -> Any:
    """Backward-compatible wrapper for the query-run service worker call."""
    return await _query_run_service().invoke_workflow(workflow, question, **kwargs)


async def execute_query_run(
    *,
    query_id: str,
    http_request: Request,
    request: QueryRequest,
    x_api_key: str | None,
    x_model: str | None,
    x_base_url: str | None,
    x_request_id: str | None,
    authorization: str | None,
    current_user: User,
    authorization_context: AuthorizationContext,
) -> None:
    """Backward-compatible wrapper for background query execution."""
    await _query_run_service().execute(
        store=_query_event_store(),
        query_id=query_id,
        http_request=http_request,
        request=request,
        x_api_key=x_api_key,
        x_model=x_model,
        x_base_url=x_base_url,
        x_request_id=x_request_id,
        authorization=authorization,
        current_user=current_user,
        authorization_context=authorization_context,
    )


async def create_query_run(
    http_request: Request,
    request: QueryRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    authorization: str | None = Header(None, alias="Authorization"),
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """受理流式查询，后续结果通过同一查询 ID 的 SSE 读取。"""
    if not authorization_context.can("queries:create"):
        raise HTTPException(status_code=403, detail="权限不足")
    store = _query_event_store()
    query_id = uuid.uuid4().hex
    store.create_run(
        query_id,
        user_id=current_user.id,
        organization_id=authorization_context.organization_id,
    )
    store.append(query_id, "accepted", {"query_id": query_id})
    asyncio.create_task(
        execute_query_run(
            query_id=query_id,
            http_request=http_request,
            request=request,
            x_api_key=x_api_key,
            x_model=x_model,
            x_base_url=x_base_url,
            x_request_id=x_request_id,
            authorization=authorization,
            current_user=current_user,
            authorization_context=authorization_context,
        )
    )
    return QueryRunAccepted(query_id=query_id)


async def stream_query_run_events(
    query_id: str,
    http_request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """以安全白名单事件回放或订阅一个短生命周期查询运行。"""
    store = _query_event_store()
    if not store.can_access(
        query_id,
        user_id=current_user.id,
        organization_id=authorization_context.organization_id,
    ):
        raise HTTPException(status_code=404, detail="查询不存在或无访问权限")
    try:
        sequence = max(0, int(last_event_id or "0"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Last-Event-ID 无效") from exc

    async def event_stream():
        async for event in iter_query_run_events(
            store=store,
            query_id=query_id,
            after_sequence=sequence,
            is_disconnected=http_request.is_disconnected,
        ):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def cancel_query_run(
    query_id: str,
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """请求协作式取消；重复调用不会制造重复终态事件。"""
    store = _query_event_store()
    if not store.can_access(
        query_id,
        user_id=current_user.id,
        organization_id=authorization_context.organization_id,
    ):
        raise HTTPException(status_code=404, detail="查询不存在或无访问权限")
    return {"query_id": query_id, "cancelled": store.request_cancel(query_id)}


async def query(
    http_request: Request,
    request: QueryRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    authorization: str | None = Header(None, alias="Authorization"),
    current_user: User = Depends(get_current_user),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """
    法律问答接口

    支持通过自定义 Header 传入用户配置：
    - X-API-Key: 用户自己的 LLM API Key
    - X-Base-URL: 用户选择的 API 基础 URL
    - X-Model: 用户选择的模型名称
    """
    request_started = time.perf_counter()
    event_id = getattr(http_request.state, "request_id", None) or x_request_id or uuid.uuid4().hex
    if not components.get("workflow"):
        raise HTTPException(status_code=503, detail="系统未初始化")
    if not authorization_context.can("queries:create"):
        raise HTTPException(status_code=403, detail="权限不足")

    if x_base_url or x_model:
        try:
            runtime_llm_config = runtime_llm_policy.validate(
                base_url=x_base_url or settings.deepseek_base_url,
                model=x_model or settings.deepseek_model,
                allow_custom=authorization_context.can("runtime_models:custom"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        x_base_url = runtime_llm_config.base_url
        x_model = runtime_llm_config.model

    try:
        logger.info(
            "处理查询 request_id=%s question_sha256=%s question_length=%s",
            event_id,
            hashlib.sha256(request.query.encode("utf-8")).hexdigest(),
            len(request.query),
        )

        knowledge_base_service = components.get("knowledge_base_service")
        if knowledge_base_service is None:
            raise HTTPException(status_code=503, detail="知识库服务未初始化")
        if hasattr(knowledge_base_service, "list_visible_knowledge_bases"):
            visible_knowledge_bases = [
                item
                for item in knowledge_base_service.list_visible_knowledge_bases(
                    organization_id=authorization_context.organization_id
                )
                if item.get("type") == "statute" and item.get("status") == "READY"
            ]
        else:  # legacy test seam; production service always exposes the visible registry.
            visible_knowledge_bases = [
                {
                    "slug": "civil-code",
                    "name": "中华人民共和国民法典",
                    "type": "statute",
                    "status": "READY",
                }
            ]
        route_decision = KnowledgeBaseRouter().route(
            request.query,
            visible_knowledge_bases,
            explicit_slugs=request.knowledge_base_ids,
        )
        selected_ids = route_decision.selected_slugs
        if not selected_ids:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "KNOWLEDGE_BASE_CLARIFICATION_REQUIRED",
                    "message": "无法可靠判断适用知识库，请选择法规库后重问。",
                    "candidates": [
                        {
                            "slug": item.slug,
                            "confidence": item.confidence,
                            "reason_code": item.reason_code,
                        }
                        for item in route_decision.candidates
                    ],
                },
            )
        try:
            version_selection, version_selections, collection_names = (
                query_execution_service.resolve_collections(
                    knowledge_base_service=knowledge_base_service,
                    query_version_service=components.get("query_version_service"),
                    selected_slugs=selected_ids,
                    organization_id=authorization_context.organization_id,
                    case_date=request.case_date,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        version_metadata = (
            {
                **version_selection.provenance,
                "as_of": version_selection.as_of.isoformat(),
                "assumption": version_selection.assumption,
                "timeline": version_selection.timeline,
            }
            if version_selection is not None
            else None
        )
        knowledge_base_routing_metadata = {
            "mode": route_decision.mode,
            "selected_slugs": selected_ids,
            "candidates": [
                {
                    "slug": candidate.slug,
                    "confidence": candidate.confidence,
                    "reason_code": candidate.reason_code,
                }
                for candidate in route_decision.candidates
            ],
        }
        version_selections_metadata = {
            slug: {
                **selection.provenance,
                "as_of": selection.as_of.isoformat(),
                "assumption": selection.assumption,
                "timeline": selection.timeline,
            }
            for slug, selection in version_selections.items()
        }

        if db_session.SessionLocal is None:
            raise HTTPException(status_code=503, detail="数据库服务未初始化")
        session_service = SessionService(db_session.SessionLocal)
        try:
            session_id, memory_turns = query_execution_service.load_or_create_session(
                session_service,
                user_id=current_user.id,
                organization_id=authorization_context.organization_id,
                requested_session_id=request.session_id,
                question=request.query,
            )
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="会话不存在或不可用") from exc

        # 保留运行时配置结构，thread_id 现在就是稳定的会话 ID。
        runtime_config = {"configurable": {"thread_id": session_id}}
        if x_api_key:
            runtime_config["user_api_key"] = x_api_key
        if x_base_url:
            runtime_config["user_base_url"] = x_base_url
        if x_model:
            runtime_config["user_model"] = x_model

        cache_scope = query_execution_service.build_cache_scope(
            user_id=current_user.id,
            session_id=session_id,
            selected_slugs=selected_ids,
            base_url=x_base_url or settings.deepseek_base_url,
            model=x_model or settings.deepseek_model,
            retrieval_version=settings.query_cache_retrieval_version,
            case_date=request.case_date,
            version_selections=version_selections,
        )
        query_cache_service = components.get("query_cache_service")
        cache_bypass = request.config.get("cache_bypass") is True
        if query_cache_service and not cache_bypass:
            cached = query_cache_service.get_exact(request.query, cache_scope)
            if cached:
                cached_response = deepcopy(cached)
                cached_response["metadata"] = {
                    **cached_response.get("metadata", {}),
                    "cache_hit": "exact",
                    "memory_turns_used": len(memory_turns),
                    "knowledge_base_routing": knowledge_base_routing_metadata,
                    **(
                        {"version_selections": version_selections_metadata}
                        if version_selections_metadata
                        else {}
                    ),
                    **({"version_selection": version_metadata} if version_metadata else {}),
                }
                session_service.record_turn(
                    user_id=current_user.id,
                    session_id=session_id,
                    question=request.query,
                    answer=cached_response["answer"],
                    intent=cached_response.get("intent"),
                    citations=cached_response.get("citations", []),
                    verification_status=cached_response.get("verification_status"),
                    metadata=cached_response["metadata"],
                    knowledge_base_slug=selected_ids[0],
                    organization_id=authorization_context.organization_id,
                )
                cached_response["query_id"] = session_id
                record_query_observability(
                    event_id=event_id,
                    organization_id=authorization_context.organization_id,
                    current_user_id=current_user.id,
                    question=request.query,
                    answer=cached_response["answer"],
                    verification_status=cached_response["verification_status"],
                    metadata=cached_response["metadata"],
                    latency_ms=round((time.perf_counter() - request_started) * 1000),
                )
                return QueryResponse(**cached_response)

        # 索引器仅承载只读 collection 与已缓存的 Embedding；按 collection 复用，
        # 不再用全局锁串行化整条查询主链。
        runtime_registry = components.get("query_runtime_registry")

        def build_indexer(collection_name: str) -> LawIndexer:
            return LawIndexer(
                persist_directory=settings.chroma_persist_directory,
                embedding_model=settings.embedding_model,
                collection_name=collection_name,
            )

        with nullcontext():
            primary_collection = collection_names[selected_ids[0]]
            scoped_indexer = (
                runtime_registry.get_or_create(
                    primary_collection, lambda: build_indexer(primary_collection)
                )
                if runtime_registry is not None
                else build_indexer(primary_collection)
            )
            query_embedding = None
            if query_cache_service and not cache_bypass:
                try:
                    query_embedding = [
                        float(value)
                        for value in scoped_indexer.embeddings.embed_query(request.query)
                    ]
                    semantic_hit = query_cache_service.get_semantic(
                        request.query,
                        cache_scope,
                        embedding=query_embedding,
                    )
                    if semantic_hit:
                        cached_response = deepcopy(semantic_hit["payload"])
                        cached_response["metadata"] = {
                            **cached_response.get("metadata", {}),
                            "cache_hit": "semantic",
                            "cache_original_query": semantic_hit["original_query"],
                            "cache_similarity": semantic_hit["similarity"],
                            "memory_turns_used": len(memory_turns),
                            "knowledge_base_routing": knowledge_base_routing_metadata,
                            **(
                                {"version_selections": version_selections_metadata}
                                if version_selections_metadata
                                else {}
                            ),
                            **({"version_selection": version_metadata} if version_metadata else {}),
                        }
                        session_service.record_turn(
                            user_id=current_user.id,
                            session_id=session_id,
                            question=request.query,
                            answer=cached_response["answer"],
                            intent=cached_response.get("intent"),
                            citations=cached_response.get("citations", []),
                            verification_status=cached_response.get("verification_status"),
                            metadata=cached_response["metadata"],
                            knowledge_base_slug=selected_ids[0],
                            organization_id=authorization_context.organization_id,
                        )
                        cached_response["query_id"] = session_id
                        record_query_observability(
                            event_id=event_id,
                            organization_id=authorization_context.organization_id,
                            current_user_id=current_user.id,
                            question=request.query,
                            answer=cached_response["answer"],
                            verification_status=cached_response["verification_status"],
                            metadata=cached_response["metadata"],
                            latency_ms=round((time.perf_counter() - request_started) * 1000),
                        )
                        return QueryResponse(**cached_response)
                except Exception as exc:
                    logger.warning("语义查询缓存不可用 error_type=%s", type(exc).__name__)
            scoped_retrievers = {}
            for slug, collection_name in collection_names.items():
                indexer = (
                    scoped_indexer
                    if slug == selected_ids[0]
                    else runtime_registry.get_or_create(
                        collection_name, lambda name=collection_name: build_indexer(name)
                    )
                    if runtime_registry is not None
                    else build_indexer(collection_name)
                )
                scoped_retrievers[slug] = LawRetriever(
                    vectorstore=indexer.vectorstore,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model,
                )
            effective_api_key = x_api_key or settings.deepseek_api_key
            effective_base_url = x_base_url or settings.deepseek_base_url
            effective_model = x_model or settings.deepseek_model
            runtime_llms = build_runtime_operation_llms(
                api_key=effective_api_key,
                base_url=effective_base_url,
                model=effective_model,
            )
            runtime_rewriter = None
            if components.get("query_rewriter") is not None:
                runtime_rewriter = QueryRewriter(
                    api_key=effective_api_key,
                    base_url=effective_base_url,
                    model=effective_model,
                    request_timeout=settings.runtime_llm_query_rewrite_timeout_seconds,
                    max_retries=settings.runtime_llm_query_rewrite_max_retries,
                )
            workflow = LegalEvidenceWorkflow(
                law_retriever=MultiKnowledgeBaseLawRetriever(
                    {
                        slug: QueryEnhancedLawRetriever(
                            retriever, runtime_rewriter, enable_hyde=settings.hyde_enabled
                        )
                        for slug, retriever in scoped_retrievers.items()
                    }
                ),
                answer_generator=build_evidence_answer_generator(
                    runtime_llms["answer"],
                    memory_turns=memory_turns,
                    repair_llm=runtime_llms["repair"],
                ),
                planner=build_evidence_planner(runtime_llms["planning"]),
                router=route_evidence_workflow,
                case_retriever=components.get("case_retriever"),
                graph_retriever=components.get("graph_retriever"),
            )
            result = await invoke_workflow_in_worker(
                workflow,
                request.query,
                knowledge_base_slugs=selected_ids,
                conversation_context=memory_turns,
                request_context={
                    "user_id": current_user.id,
                    "organization_id": authorization_context.organization_id,
                    "session_id": session_id,
                    "model_id": effective_model,
                },
                event_sink=getattr(http_request.state, "workflow_event_sink", None),
                is_cancel_requested=getattr(http_request.state, "workflow_cancel_requested", None),
            )
        if cache_bypass:
            result.metadata["cache_bypassed"] = True

        result.metadata["memory_turns_used"] = len(memory_turns)
        result.metadata["knowledge_base_routing"] = knowledge_base_routing_metadata
        if version_selections_metadata:
            result.metadata["version_selections"] = version_selections_metadata
        if version_metadata is not None:
            result.metadata["version_selection"] = version_metadata
        query_id = session_id

        # 处理引文格式
        if result.citations and hasattr(result.citations[0], "to_dict"):
            citations_safe = [c.to_dict() for c in result.citations]
        else:
            citations_safe = [
                {
                    "article_id": c.article_id if hasattr(c, "article_id") else str(c),
                    "citation_text": c.citation_text if hasattr(c, "citation_text") else "",
                    "original_text": c.original_text if hasattr(c, "original_text") else "",
                    "is_verified": c.is_verified if hasattr(c, "is_verified") else False,
                    "knowledge_base_slug": getattr(c, "knowledge_base_slug", None),
                    "version_id": getattr(c, "version_id", None),
                    "effective_from": getattr(c, "effective_from", None),
                    "effective_to": getattr(c, "effective_to", None),
                    "source_url": getattr(c, "source_url", None),
                    "content_hash": getattr(c, "content_hash", None),
                    "source_type": getattr(c, "source_type", None),
                    "retrieval_paths": list(getattr(c, "retrieval_paths", []) or []),
                }
                for c in result.citations
            ]
        if version_selection is not None:
            primary_slug = selected_ids[0]
            for citation in citations_safe:
                # 多知识库引用优先使用证据账本带回的逐条版本信息；仅为主库的缺失字段补值。
                if citation.get("knowledge_base_slug") not in (None, primary_slug):
                    continue
                for field, value in version_selection.provenance.items():
                    if not citation.get(field):
                        citation[field] = value

        # v2.4: 统一由会话服务持久化、更新时间并在通过校验时更新画像。
        try:
            session_service.record_turn(
                user_id=current_user.id,
                session_id=session_id,
                question=request.query,
                answer=result.answer,
                intent=result.intent,
                citations=citations_safe,
                verification_status=result.verification_status,
                metadata=result.metadata,
                knowledge_base_slug=selected_ids[0],
            )
        except Exception as exc:
            logger.warning("聊天历史保存失败 error_type=%s", type(exc).__name__)

        # 转换为响应格式
        response = QueryResponse(
            query_id=query_id,
            query=result.query,
            answer=result.answer,
            intent=result.intent,
            citations=citations_safe,
            verification_status=result.verification_status,
            verification_issues=result.verification_issues,
            sub_questions=result.sub_questions,
            metadata=result.metadata,
        )
        if query_cache_service and not cache_bypass:
            try:
                payload = response.model_dump()
                if is_cacheable_query_result(payload):
                    query_cache_service.set_exact(request.query, cache_scope, payload)
                    if query_embedding is not None:
                        query_cache_service.set_semantic(
                            request.query,
                            cache_scope,
                            payload,
                            embedding=query_embedding,
                        )
            except Exception as exc:
                logger.warning("查询缓存写入失败 error_type=%s", type(exc).__name__)
        record_query_observability(
            event_id=event_id,
            organization_id=authorization_context.organization_id,
            current_user_id=current_user.id,
            question=request.query,
            answer=response.answer,
            verification_status=response.verification_status,
            metadata={
                **response.metadata,
                "citation_count": len(response.citations),
                "knowledge_base_slug": selected_ids[0],
            },
            latency_ms=round((time.perf_counter() - request_started) * 1000),
        )
        return response

    except (HTTPException, QueryCancelled):
        raise
    except Exception as exc:
        logger.error(
            "查询处理失败 request_id=%s error_type=%s",
            event_id,
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="查询处理失败，请稍后重试") from exc


def register_query_route_service() -> None:
    """Expose legacy query orchestration through the runtime-owned route seam."""

    components.register(
        "query_route_service",
        QueryRouteService(
            get_event_store=lambda: _query_event_store(),
            execute_query_run=lambda **kwargs: execute_query_run(**kwargs),
            execute_query=lambda **kwargs: query(**kwargs),
            iterate_events=lambda **kwargs: iter_query_run_events(**kwargs),
        ),
    )


register_query_route_service()


# ==================== 启动服务 ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host=settings.api_host, port=settings.api_port, reload=True)
