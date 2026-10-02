"""
FastAPI 后端服务 — LexRAG API

提供 RESTful API 接口
v1.7: 新增认证系统、Prompt 管理、数据库、Langfuse 可观测性
"""

# ⚠️ HF_ENDPOINT 必须在所有 import 之前设置，否则 sentence_transformers 会直连 huggingface.co
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import logging
import json
import threading
import time
import uuid
import re
from copy import deepcopy
from urllib.parse import urlparse
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request, Header, Query, File, Form, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from config import settings, get_project_root
from src.utils.embedding_factory import create_embeddings
from src.agent.state import QueryResult
from src.retrieval.intent_router import IntentRouter
from src.retrieval.law_retriever import LawRetriever
from src.ingestion.indexer import LawIndexer
from src.graph.law_graph import LawGraph
from src.graph.builder import GraphBuilder
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.context_compressor import ContextCompressor
from src.retrieval.case_retriever import CaseRetriever
from src.retrieval.graph_retriever import GraphRetriever
from src.ingestion.law_parser import LawParser
from src.ingestion.chunker import StructuredLawChunker

# v1.7: 新增模块
from app.db.session import init_db
from app.db import session as db_session
from app.api.auth import get_current_user, router as auth_router
from app.api.admin import (
    get_authorization_context,
    router as admin_router,
)
from app.api.law_updates import router as law_updates_router
from app.api.prompts import router as prompts_router
from app.api.favorites import router as favorites_router
from app.api.scenarios import router as scenarios_router
from app.api.sessions import router as sessions_router
from app.services.langfuse_helper import flush_langfuse
from app.services.langfuse_helper import create_llm
from app.services.knowledge_base_service import KnowledgeBaseBusyError, KnowledgeBaseService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_result_service import DocumentResultService
from app.services.case_ingestion_service import CaseIngestionService
from app.services.query_cache_service import QueryCacheService
from app.services.session_service import ConversationTurn, SessionNotFoundError, SessionService
from app.services.audit_service import AuditService
from app.services.usage_service import UsageService
from app.services.authorization_service import AuthorizationContext
from app.services.metrics import record_query_metrics
from src.ingestion.case_ocr import count_pdf_pages
from src.ingestion.annual_case_indexer import AnnualCaseIndexer
from src.retrieval.annual_case_retriever import AnnualCaseRetriever
from app.tasks.document_tasks import process_document_task
from app.services.prompt_service import seed_default_prompts
from app.models.user import User
from src.workflow.legal_evidence_workflow import (
    LegalEvidenceWorkflow,
    QueryEnhancedLawRetriever,
    RouteDecision,
)

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format
)
logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

class QueryRequest(BaseModel):
    """查询请求"""
    query: str = Field(..., description="用户问题")
    session_id: Optional[str] = Field(None, description="会话ID")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="配置参数")
    knowledge_base_ids: List[str] = Field(default_factory=list, description="限定检索的知识库 ID")


class QueryResponse(BaseModel):
    """查询响应"""
    query_id: str
    query: str
    answer: str
    intent: str
    citations: List[Dict[str, Any]]
    verification_status: str
    verification_issues: List[str]
    sub_questions: List[Dict[str, str]]
    metadata: Dict[str, Any]


class UploadRequest(BaseModel):
    """上传请求"""
    content: str = Field(..., description="法律文档内容")
    law_name: str = Field(..., description="法律名称")
    version: str = Field("v1.0", description="版本号")


class GraphQueryRequest(BaseModel):
    """图谱查询请求"""
    article_id: Optional[str] = Field(None, description="法条ID")
    source: Optional[str] = Field(None, description="起始法条")
    target: Optional[str] = Field(None, description="目标法条")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    timestamp: str
    version: str
    components: Dict[str, Any]


class KnowledgeBaseCreateRequest(BaseModel):
    """创建法规知识库的请求。"""

    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    law_area: str = Field(..., min_length=1, max_length=64)


class KnowledgeBaseRebuildRequest(BaseModel):
    """重建法规知识库的原始法条文本。"""

    content: str = Field(..., min_length=1)


def _require_knowledge_base_access(
    slug: str, context: AuthorizationContext, *, manage: bool = False
) -> None:
    """统一执行组织级知识库可见性校验，避免 slug 成为越权入口。"""
    required_permission = "knowledge_bases:manage" if manage else "knowledge_bases:read"
    if not context.can(required_permission):
        raise HTTPException(status_code=403, detail="权限不足")
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    try:
        service.get_visible_knowledge_base(
            slug,
            organization_id=context.organization_id,
            require_owner=manage,
        )
    except ValueError as exc:
        # 统一 404，避免根据 slug 探测其他组织是否存在知识库。
        raise HTTPException(status_code=404, detail="知识库不存在或无访问权限") from exc


# ==================== 全局组件 ====================

components: Dict[str, Any] = {}
query_results: Dict[str, Any] = {}
scoped_query_lock = threading.Lock()


def is_cacheable_query_result(payload: Dict[str, Any]) -> bool:
    """仅缓存通过证据校验且未被工作流标记为不可缓存的回答。"""
    return (
        payload.get("verification_status") == "pass"
        and payload.get("metadata", {}).get("cacheable", True) is True
    )


def record_query_observability(
    *,
    event_id: str,
    organization_id: int,
    current_user_id: int,
    question: str,
    answer: str,
    verification_status: str,
    metadata: Dict[str, Any],
    latency_ms: int,
) -> None:
    """审计/统计失败只能旁路，不能影响已验证的法律问答响应。"""
    audit_service = components.get("audit_service")
    usage_service = components.get("usage_service")
    record_query_metrics(
        verification_status=verification_status,
        cache_hit=str(metadata.get("cache_hit", "none")),
        latency_ms=latency_ms,
    )
    if audit_service is None or usage_service is None:
        return
    try:
        created = audit_service.append_query(
            event_id=event_id,
            organization_id=organization_id,
            actor_user_id=current_user_id,
            request_id=event_id,
            question=question,
            answer=answer,
            verification_status=verification_status,
            metadata={
                "cache_hit": metadata.get("cache_hit", "none"),
                "law_area": metadata.get("law_area"),
                "knowledge_base": metadata.get("knowledge_base_slug"),
                "citation_count": len(metadata.get("citations", [])),
            },
        )
        if created:
            usage_service.record_query(
                event_id=event_id,
                organization_id=organization_id,
                actor_user_id=current_user_id,
                latency_ms=latency_ms,
                estimated_tokens=int(metadata.get("estimated_tokens") or 0),
            )
    except Exception as exc:
        logger.warning("查询审计或统计写入失败，已旁路: %s", exc)


def build_evidence_answer_generator(llm, *, memory_turns: list[ConversationTurn] | None = None):
    """将本次证据账本转换成唯一允许引用的生成上下文。"""
    memory_sections = []
    for turn in memory_turns or []:
        citations = "、".join(turn.verified_citations) or "（无已验证引用）"
        memory_sections.append(
            f"用户：{turn.question}\n助手：{turn.answer}\n已验证历史引用：{citations}"
        )
    memory_text = "\n\n".join(memory_sections) or "（本会话尚无历史）"

    def generate(question, evidence, issues=None):
        statutes = [item for item in evidence if item.source_type == "statute"]
        evidence_text = "\n\n".join(
            f"【{item.law_name}第{item.normalized_article_id}条】\n{item.content}"
            for item in statutes
        )
        repair_instruction = ""
        if issues:
            repair_instruction = (
                "\n上一次回答未通过引用校验，问题如下：\n- "
                + "\n- ".join(issues)
                + "\n请只使用下列证据重写回答。"
            )
        prompt = f"""你是法律信息助手。请仅依据下面的本次检索证据回答用户问题。

用户问题：{question}

历史上下文（仅帮助理解，不构成本轮证据）：
{memory_text}

可引用证据：
{evidence_text}

要求：
1. 每个法律结论必须有且只能有一个来自证据的法条引用，格式严格为【法律名称第N条】。
2. 不得引用未出现在证据中的法律、条号或案例；证据不足时明确说明限制。
3. 新法律结论和引用只能来自本轮检索证据，历史中的法条不得作为本轮引用。
4. 不构成法律建议，提示用户在需要时咨询专业律师。{repair_instruction}
"""
        return llm.invoke(prompt).content.strip()

    return generate


def build_evidence_planner(llm):
    """复杂问题的可选结构化拆解；解析失败由工作流降级。"""
    def plan(question):
        prompt = f"""将以下法律问题拆成最多 4 个互不重复的检索子问题。
只输出 JSON 数组，每项格式为 {{"question": "...", "depends_on": ""}}。
问题：{question}"""
        content = llm.invoke(prompt).content.strip().replace("```json", "").replace("```", "")
        result = json.loads(content)
        if not isinstance(result, list):
            raise ValueError("planning output must be a JSON array")
        return result

    return plan


def route_evidence_workflow(question: str) -> RouteDecision:
    """可预测的关键词路由；法规检索始终由工作流执行。"""
    normalized = question.lower()
    comparative = any(word in normalized for word in ("区别", "对比", "不同", "分别"))
    procedural = any(word in normalized for word in ("怎么办", "流程", "仲裁", "起诉", "维权"))
    include_case = any(word in normalized for word in ("案例", "判例", "法院怎么判"))
    include_graph = comparative or any(word in normalized for word in ("依据", "关联", "适用"))
    if comparative:
        intent = "comparative"
    elif procedural:
        intent = "procedural"
    elif include_case:
        intent = "analytical"
    else:
        intent = "factual"
    return RouteDecision(intent=intent, include_case=include_case, include_graph=include_graph)


def initialize_components():
    """初始化组件"""
    global components
    
    try:
        knowledge_base_service = None
        document_ingestion_service = None
        document_result_service = None
        case_ingestion_service = None
        annual_case_retriever = None
        query_cache_service = None
        try:
            import redis
            query_cache_service = QueryCacheService(
                redis.Redis.from_url(settings.redis_url, decode_responses=True),
                ttl_seconds=settings.query_cache_ttl_seconds,
                semantic_threshold=settings.query_cache_semantic_threshold,
            )
        except Exception as exc:
            logger.warning(f"查询缓存初始化失败，将旁路缓存: {exc}")
        if db_session.SessionLocal is not None:
            knowledge_base_service = KnowledgeBaseService(db_session.SessionLocal)
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
                logger.warning(f"年度案例检索器初始化失败: {exc}")

        # 初始化意图路由器
        intent_router = IntentRouter(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model
        )
        
        # 初始化向量存储
        law_indexer = LawIndexer(
            persist_directory=settings.chroma_persist_directory,
            embedding_model=settings.embedding_model,
            collection_name=settings.law_collection_name
        )
        
        # 初始化法条检索器
        law_retriever = LawRetriever(
            vectorstore=law_indexer.vectorstore,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model
        )
        
        # 判例检索器
        case_retriever = None
        try:
            from langchain_community.vectorstores import Chroma
            case_db_path = Path(settings.chroma_persist_directory) / "cases"
            if case_db_path.exists():
                case_embeddings = create_embeddings(
                    model_path=settings.local_embedding_model_path,
                    zhipuai_api_key=settings.zhipuai_api_key,
                    zhipuai_model=settings.embedding_model,
                )
                case_vectorstore = Chroma(
                    collection_name=settings.case_collection_name,
                    embedding_function=case_embeddings,
                    persist_directory=str(case_db_path)
                )
                case_retriever = CaseRetriever(
                    case_vectorstore=case_vectorstore,
                    law_retriever=law_retriever,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model
                )
                logger.info("判例检索器初始化成功")
            else:
                logger.info("判例数据库不存在，跳过判例检索器初始化")
        except Exception as e:
            logger.warning(f"判例检索器初始化失败: {e}")

        # BM25检索器
        bm25_retriever = None
        if settings.bm25_enabled:
            try:
                bm25_retriever = BM25Retriever()
                # 从ChromaDB加载文档构建索引
                try:
                    collection = law_indexer.vectorstore._collection
                    all_data = collection.get(include=["documents", "metadatas"])
                    if all_data and all_data.get("documents"):
                        bm25_docs = []
                        for i, doc_content in enumerate(all_data["documents"]):
                            meta = all_data["metadatas"][i] if all_data.get("metadatas") else {}
                            bm25_docs.append({
                                "doc_id": meta.get("article_id", f"doc_{i}"),
                                "content": doc_content,
                                "metadata": meta
                            })
                        bm25_retriever.build_index(bm25_docs)
                except Exception as e:
                    logger.warning(f"BM25索引构建失败: {e}")
                    bm25_retriever = None
            except Exception as e:
                logger.warning(f"BM25初始化失败: {e}")

        # Reranker
        reranker = None
        if settings.reranker_enabled:
            try:
                reranker = CrossEncoderReranker(model_name=settings.reranker_model)
            except Exception as e:
                logger.warning(f"Reranker初始化失败: {e}")

        # Query Rewriter
        query_rewriter = None
        if settings.query_rewriting_enabled:
            try:
                query_rewriter = QueryRewriter(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model
                )
            except Exception as e:
                logger.warning(f"Query Rewriter初始化失败: {e}")

        # Context Compressor
        context_compressor = None
        if settings.context_compress_enabled:
            try:
                context_compressor = ContextCompressor(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    model=settings.deepseek_model
                )
            except Exception as e:
                logger.warning(f"Context Compressor初始化失败: {e}")
        
        # 初始化知识图谱
        law_graph_path = get_project_root() / settings.law_graph_path
        if law_graph_path.exists():
            law_graph = LawGraph.from_json(str(law_graph_path))
        else:
            law_graph = LawGraph()
        
        # v2.1 的工作流按请求创建，以支持用户选择的知识库和运行时模型配置。
        # 此处保留就绪标记供健康检查和已有 API 契约使用，不再初始化 ReAct Agent。
        workflow = "evidence-v2.1"
        graph_retriever = GraphRetriever(law_graph.graph)
        
        components = {
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
            "document_ingestion_service": document_ingestion_service,
            "document_result_service": document_result_service,
            "case_ingestion_service": case_ingestion_service,
            "annual_case_retriever": annual_case_retriever,
            "query_cache_service": query_cache_service,
        }
        
        logger.info("组件初始化完成")
        return True
        
    except Exception as e:
        logger.error(f"组件初始化失败: {e}")
        return False


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
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
            components["audit_service"] = AuditService(db_session.SessionLocal)
            components["usage_service"] = UsageService(db_session.SessionLocal)
        logger.info("数据库已就绪")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

    # 初始化检索组件
    initialize_components()

    # v1.7: 初始化默认 Prompt 模板
    try:
        from app.db.session import SessionLocal
        if SessionLocal:
            db = SessionLocal()
            try:
                seed_default_prompts(db)
            finally:
                db.close()
    except Exception as e:
        logger.warning(f"默认 Prompt 初始化失败（非致命）: {e}")

    # 打印 Embedding 来源
    from src.utils.embedding_factory import get_embedding_source
    logger.info(f"Embedding 来源: {get_embedding_source()}")

    yield

    # v1.7: 刷新 Langfuse 缓冲区
    flush_langfuse()
    logger.info("LexRAG 应用已关闭")


# ==================== 创建应用 ====================

app = FastAPI(
    title="LexRAG 法律智能知识平台 API",
    description="基于结构化RAG + Multi-Agent + 法条自校验的法律智能知识平台API",
    version="3.0.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    # 浏览器凭据不能与通配 Origin 一起使用；本机开发和 Docker 演示显式放行。
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:8080", "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/metrics", make_asgi_app())

# v1.7: 注册新路由
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(law_updates_router)
app.include_router(prompts_router)
app.include_router(favorites_router)
app.include_router(scenarios_router)
app.include_router(sessions_router)


# ==================== API端点 ====================

@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径"""
    return {
        "message": "LexRAG 法律智能知识平台 API",
        "version": "3.0.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy" if components else "initializing",
        timestamp=datetime.now().isoformat(),
        version="3.0.0",
        components={
            "workflow": "ready" if components.get("workflow") else "not_ready",
            "law_indexer": "ready" if components.get("law_indexer") else "not_ready",
            "law_graph": "ready" if components.get("law_graph") else "not_ready"
        }
    )


@app.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    """返回当前本机演示可验证的首页统计，不使用前端常量。"""
    del current_user
    service = components.get("case_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="案例服务未初始化")
    return service.get_statistics()


@app.get("/knowledge-bases")
async def list_knowledge_bases(
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """返回已注册知识库及其索引状态。"""
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    if not authorization_context.can("knowledge_bases:read"):
        raise HTTPException(status_code=403, detail="权限不足")
    return {"items": service.list_visible_knowledge_bases(organization_id=authorization_context.organization_id)}


@app.post("/knowledge-bases", status_code=201)
async def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """创建一个空的法规知识库注册记录。"""
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    if not authorization_context.can("knowledge_bases:manage"):
        raise HTTPException(status_code=403, detail="权限不足")
    return service.create_knowledge_base(
        name=request.name,
        slug=request.slug,
        law_area=request.law_area,
        organization_id=authorization_context.organization_id,
    )


@app.post("/document-libraries", status_code=201)
async def create_document_library(
    request: KnowledgeBaseCreateRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """创建一个接收 PDF/Word 的自定义文档知识库。"""
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    if not authorization_context.can("knowledge_bases:manage"):
        raise HTTPException(status_code=403, detail="权限不足")
    return service.create_document_library(
        name=request.name,
        slug=request.slug,
        law_area=request.law_area,
        organization_id=authorization_context.organization_id,
    )


@app.post("/document-libraries/{slug}/documents", status_code=202)
async def upload_document(
    slug: str,
    file: UploadFile = File(...),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(120),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """保存上传文件并投递 Celery 任务，响应不等待解析完成。"""
    service = components.get("document_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档解析服务未初始化")
    _require_knowledge_base_access(slug, authorization_context, manage=True)
    original_filename = file.filename or "upload"
    incoming_path = Path(settings.document_uploads_path) / ".incoming" / f"{uuid.uuid4()}_{original_filename}"
    incoming_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        incoming_path.write_bytes(await file.read())
        return service.submit_document(
            knowledge_base_slug=slug,
            source_path=incoming_path,
            original_filename=original_filename,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "相同文件" in message else 422
        raise HTTPException(status_code=status_code, detail=message) from exc
    finally:
        await file.close()
        if incoming_path.exists():
            incoming_path.unlink()


@app.post("/document-libraries/{slug}/documents/batch", status_code=202)
async def upload_documents(
    slug: str,
    files: list[UploadFile] = File(...),
    chunk_size: int = Form(800),
    chunk_overlap: int = Form(120),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """逐个创建批量上传任务，单一文件的校验失败不影响其余文件。"""
    service = components.get("document_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档解析服务未初始化")
    _require_knowledge_base_access(slug, authorization_context, manage=True)
    incoming_paths: list[Path] = []
    submissions: list[dict] = []
    try:
        for file in files:
            original_filename = Path(file.filename or "upload").name
            incoming_path = (
                Path(settings.document_uploads_path)
                / ".incoming"
                / f"{uuid.uuid4()}_{original_filename}"
            )
            incoming_path.parent.mkdir(parents=True, exist_ok=True)
            incoming_path.write_bytes(await file.read())
            incoming_paths.append(incoming_path)
            submissions.append(
                {"source_path": incoming_path, "original_filename": original_filename}
            )
        return {
            "items": service.submit_documents(
                knowledge_base_slug=slug,
                submissions=submissions,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        }
    finally:
        for file in files:
            await file.close()
        for incoming_path in incoming_paths:
            if incoming_path.exists():
                incoming_path.unlink()


@app.get("/document-libraries/{slug}/documents")
async def list_documents(
    slug: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """返回某一自定义文档库的全部处理任务。"""
    service = components.get("document_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档解析服务未初始化")
    _require_knowledge_base_access(slug, authorization_context)
    try:
        return {"items": service.list_documents(slug)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/documents/{document_id}")
async def get_document(document_id: str, authorization_context: AuthorizationContext = Depends(get_authorization_context)):
    """获取任务实时状态，供前端轮询。"""
    service = components.get("document_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档解析服务未初始化")
    _require_document_access(document_id, authorization_context)
    try:
        return service.get_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_document_access(document_id: str, context: AuthorizationContext, *, manage: bool = False) -> None:
    """文档 ID 不可绕过知识库的组织隔离。"""
    service = components.get("document_result_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档结果服务未初始化")
    try:
        slug = service.get_knowledge_base_slug(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="文档不存在或无访问权限") from exc
    _require_knowledge_base_access(slug, context, manage=manage)


@app.get("/documents/{document_id}/result")
async def get_document_result(document_id: str, authorization_context: AuthorizationContext = Depends(get_authorization_context)):
    """返回可追溯的文档解析摘要，不暴露内部文件路径。"""
    service = components.get("document_result_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档结果服务未初始化")
    _require_document_access(document_id, authorization_context)
    try:
        return service.get_result(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/documents/{document_id}/pages")
async def list_document_pages(
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """分页读取文档的逐页文本、OCR 来源和表格摘要。"""
    service = components.get("document_result_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档结果服务未初始化")
    _require_document_access(document_id, authorization_context)
    try:
        return service.list_pages(document_id, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/documents/{document_id}/relations")
async def list_document_relations(document_id: str, authorization_context: AuthorizationContext = Depends(get_authorization_context)):
    """返回该文档已建立且可解释的关联边。"""
    service = components.get("document_result_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档结果服务未初始化")
    _require_document_access(document_id, authorization_context)
    try:
        return service.list_relations(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/cases")
async def list_cases(
    domain: Optional[str] = Query(default=None, description="法律领域"),
    case_cause: Optional[str] = Query(default=None, description="案由"),
    source_id: Optional[int] = Query(default=None, ge=1, description="案例源 ID"),
):
    """读取独立案例库，可按领域、案由或来源筛选。"""
    service = components.get("case_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="案例库服务未初始化")
    return {
        "items": service.list_cases(
            domain=domain,
            case_cause=case_cause,
            source_id=source_id,
        )
    }


@app.get("/case-sources")
async def list_case_sources(
    domain: Optional[str] = Query(default=None, description="法律领域"),
):
    """返回年度案例汇编的真实来源信息和 OCR 处理进度。"""
    service = components.get("case_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="案例库服务未初始化")
    return {"items": service.list_sources(domain=domain)}


@app.get("/cases/{case_id}")
async def get_case(case_id: str):
    """读取单案结构化结果及其原始 PDF 页码范围。"""
    service = components.get("case_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="案例库服务未初始化")
    try:
        return service.get_case(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/cases/{case_id}/similar")
async def similar_cases(
    case_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
):
    """在年度案例独立向量库中检索相似案例，并对相同案由加分。"""
    retriever = components.get("annual_case_retriever")
    if retriever is None:
        raise HTTPException(status_code=503, detail="年度案例检索服务未初始化")
    try:
        return {"items": retriever.similar_cases(case_id, top_k=top_k)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/documents/{document_id}/retry", status_code=202)
async def retry_document(document_id: str, authorization_context: AuthorizationContext = Depends(get_authorization_context)):
    """重新投递一个失败文档的原始处理任务。"""
    service = components.get("document_ingestion_service")
    if service is None:
        raise HTTPException(status_code=503, detail="文档解析服务未初始化")
    _require_document_access(document_id, authorization_context, manage=True)
    try:
        return service.retry_document(document_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "仅失败" in message else 404
        raise HTTPException(status_code=status_code, detail=message) from exc


@app.post("/knowledge-bases/{slug}/rebuild")
async def rebuild_knowledge_base(
    slug: str,
    request: KnowledgeBaseRebuildRequest,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """将法条文本解析、切分并写入指定知识库的专属 collection。"""
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    _require_knowledge_base_access(slug, authorization_context, manage=True)
    try:
        return service.rebuild_knowledge_base(slug, content=request.content)
    except KnowledgeBaseBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/knowledge-bases/{slug}/laws")
async def list_knowledge_base_laws(
    slug: str,
    start_article: Optional[int] = Query(default=None, ge=1),
    end_article: Optional[int] = Query(default=None, ge=1),
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """读取选定法规知识库的真实法条。"""
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    _require_knowledge_base_access(slug, authorization_context)
    try:
        return {
            "items": service.list_law_articles(
                slug,
                start_article=start_article,
                end_article=end_article,
            )
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/knowledge-bases/{slug}", status_code=204)
async def delete_knowledge_base(
    slug: str,
    authorization_context: AuthorizationContext = Depends(get_authorization_context),
):
    """删除非索引中的知识库及其专属向量 collection。"""
    service = components.get("knowledge_base_service")
    if service is None:
        raise HTTPException(status_code=503, detail="知识库服务未初始化")
    _require_knowledge_base_access(slug, authorization_context, manage=True)
    try:
        service.delete_knowledge_base(slug)
    except KnowledgeBaseBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/query", response_model=QueryResponse)
async def query(
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
    if not components.get("workflow"):
        raise HTTPException(status_code=503, detail="系统未初始化")
    if not authorization_context.can("queries:create"):
        raise HTTPException(status_code=403, detail="权限不足")

    if x_base_url:
        parsed_base_url = urlparse(x_base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise HTTPException(status_code=422, detail="X-Base-URL 必须是有效的 HTTP(S) Base URL")
    if x_model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", x_model):
        raise HTTPException(status_code=422, detail="X-Model 格式无效")

    try:
        logger.info(f"处理查询: {request.query}")

        selected_ids = request.knowledge_base_ids or ["civil-code"]
        if len(selected_ids) != 1:
            raise HTTPException(status_code=400, detail="当前版本一次只能选择一个知识库")
        knowledge_base_service = components.get("knowledge_base_service")
        if knowledge_base_service is None:
            raise HTTPException(status_code=503, detail="知识库服务未初始化")
        try:
            collection_name = knowledge_base_service.get_ready_collection_name_for_organization(
                selected_ids[0], organization_id=authorization_context.organization_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if db_session.SessionLocal is None:
            raise HTTPException(status_code=503, detail="数据库服务未初始化")
        session_service = SessionService(db_session.SessionLocal)
        try:
            if request.session_id:
                session_payload = session_service.get_for_user(
                    user_id=current_user.id, session_id=request.session_id,
                    organization_id=authorization_context.organization_id,
                )
            else:
                session_payload = session_service.create(
                    user_id=current_user.id, initial_question=request.query,
                    organization_id=authorization_context.organization_id,
                )
            session_id = session_payload["id"]
            memory_turns = session_service.load_memory(
                user_id=current_user.id, session_id=session_id,
                organization_id=authorization_context.organization_id,
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

        # v2.0：缓存作用域不保存 API Key/JWT 原文；授权令牌只使用不可逆摘要做用户隔离。
        user_scope = f"user:{current_user.id}"
        cache_scope = {
            "user_scope": user_scope,
            "session_id": session_id,
            "knowledge_base_slug": selected_ids[0],
            "base_url": x_base_url or settings.deepseek_base_url,
            "model": x_model or settings.deepseek_model,
            "prompt_version": "runtime-v1",
            "retrieval_version": settings.query_cache_retrieval_version,
        }
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
                    event_id=x_request_id or str(uuid.uuid4()),
                    organization_id=authorization_context.organization_id,
                    current_user_id=current_user.id,
                    question=request.query,
                    answer=cached_response["answer"],
                    verification_status=cached_response["verification_status"],
                    metadata=cached_response["metadata"],
                    latency_ms=round((time.perf_counter() - request_started) * 1000),
                )
                return QueryResponse(**cached_response)

        # 每次请求使用目标 collection 构造独立检索器；工具注册表为模块级状态，
        # 因此用锁避免并发请求在不同知识库之间交叉。
        with scoped_query_lock:
            scoped_indexer = LawIndexer(
                persist_directory=settings.chroma_persist_directory,
                embedding_model=settings.embedding_model,
                collection_name=collection_name,
            )
            query_embedding = None
            if query_cache_service and not cache_bypass:
                try:
                    query_embedding = [float(value) for value in scoped_indexer.embeddings.embed_query(request.query)]
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
                            event_id=x_request_id or str(uuid.uuid4()),
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
                    logger.warning(f"语义查询缓存不可用，将继续正常检索: {exc}")
            scoped_retriever = LawRetriever(
                vectorstore=scoped_indexer.vectorstore,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_model,
            )
            effective_api_key = x_api_key or settings.deepseek_api_key
            effective_base_url = x_base_url or settings.deepseek_base_url
            effective_model = x_model or settings.deepseek_model
            runtime_llm = create_llm(
                api_key=effective_api_key,
                base_url=effective_base_url,
                model=effective_model,
                temperature=0.1,
            )
            runtime_rewriter = None
            if components.get("query_rewriter") is not None:
                runtime_rewriter = QueryRewriter(
                    api_key=effective_api_key,
                    base_url=effective_base_url,
                    model=effective_model,
                )
            workflow = LegalEvidenceWorkflow(
                law_retriever=QueryEnhancedLawRetriever(scoped_retriever, runtime_rewriter),
                answer_generator=build_evidence_answer_generator(
                    runtime_llm, memory_turns=memory_turns
                ),
                planner=build_evidence_planner(runtime_llm),
                router=route_evidence_workflow,
                case_retriever=components.get("case_retriever"),
                graph_retriever=components.get("graph_retriever"),
            )
            result = workflow.query(
                request.query,
                knowledge_base_slug=selected_ids[0],
            )
        if cache_bypass:
            result.metadata["cache_bypassed"] = True

        # 保存结果到内存
        result.metadata["memory_turns_used"] = len(memory_turns)
        query_id = session_id
        query_results[query_id] = result

        # 处理引文格式
        if result.citations and hasattr(result.citations[0], 'to_dict'):
            citations_safe = [c.to_dict() for c in result.citations]
        else:
            citations_safe = [
                {
                    "article_id": c.article_id if hasattr(c, 'article_id') else str(c),
                    "citation_text": c.citation_text if hasattr(c, 'citation_text') else "",
                    "original_text": c.original_text if hasattr(c, 'original_text') else "",
                    "is_verified": c.is_verified if hasattr(c, 'is_verified') else False
                }
                for c in result.citations
            ]

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
        except Exception as e:
            logger.warning(f"聊天历史保存失败（非致命）: {e}")

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
            metadata=result.metadata
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
                logger.warning(f"查询缓存写入失败，将继续返回结果: {exc}")
        record_query_observability(
            event_id=x_request_id or str(uuid.uuid4()),
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload")
async def upload_law(request: UploadRequest, background_tasks: BackgroundTasks):
    """
    上传法律文档
    
    Args:
        request: 上传请求
        background_tasks: 后台任务
        
    Returns:
        上传结果
    """
    if not components.get("law_indexer"):
        raise HTTPException(status_code=503, detail="系统未初始化")
    
    try:
        # 解析法律文档
        parser = LawParser()
        articles = parser.parse_law_content(request.content, request.law_name)
        
        # 切分
        chunker = StructuredLawChunker(version=request.version)
        chunks = chunker.chunk_articles(articles)
        
        # 索引
        indexer = components["law_indexer"]
        count = indexer.build_index(chunks)
        
        return {
            "status": "success",
            "message": f"成功索引 {count} 个法条",
            "article_count": len(articles),
            "chunk_count": count
        }
        
    except Exception as e:
        logger.error(f"上传失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph")
async def get_graph(law_name: str | None = Query(None)):
    """
    获取知识图谱信息
    
    Returns:
        图谱信息
    """
    if not components.get("law_graph"):
        raise HTTPException(status_code=503, detail="图谱未初始化")
    
    try:
        graph = components["law_graph"]
        raw = graph.visualize_data()

        available_laws = sorted({str(n.get("law_name", "")) for n in raw.get("nodes", []) if n.get("law_name")})
        selected_nodes = [
            node for node in raw.get("nodes", [])
            if law_name is None or node.get("law_name") == law_name
        ]
        selected_ids = {node.get("id") for node in selected_nodes}

        # 转译为前端 ECharts 格式，节点 ID 与边端点保持一致。
        nodes = []
        for n in selected_nodes:
            in_deg = n.get("citation_count", 0)
            nodes.append({
                "id": n.get("id", ""),
                "name": f"第{n.get('article_number')}条" if n.get("article_number") else n.get("label", ""),
                "symbolSize": max(18, 20 + in_deg * 4),
                "category": 0,
                "law_name": n.get("law_name", ""),
            })
        links = [
            {"source": e["from"], "target": e["to"]}
            for e in raw.get("edges", [])
            if e.get("from") in selected_ids and e.get("to") in selected_ids
        ]

        return {
            "statistics": graph.get_statistics(),
            "most_cited": graph.get_most_cited(top_n=10),
            "available_laws": available_laws,
            "visualization_data": {"nodes": nodes, "links": links}
        }
        
    except Exception as e:
        logger.error(f"获取图谱失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graph/query")
async def query_graph(request: GraphQueryRequest):
    """
    查询图谱
    
    Returns:
        查询结果
    """
    if not components.get("law_graph"):
        raise HTTPException(status_code=503, detail="图谱未初始化")
    
    try:
        graph = components["law_graph"]
        
        if request.article_id:
            # 获取法条的引用链
            citation_chain = graph.get_citation_chain(request.article_id)
            return citation_chain
        
        elif request.source and request.target:
            # 查找最短路径
            path = graph.find_shortest_path(request.source, request.target)
            return {"path": path}
        
        else:
            raise HTTPException(status_code=400, detail="请提供article_id或source+target")
        
    except Exception as e:
        logger.error(f"图谱查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/verify/{query_id}")
async def verify_result(query_id: str):
    """
    验证查询结果
    
    Args:
        query_id: 查询ID
        
    Returns:
        验证结果
    """
    if query_id not in query_results:
        raise HTTPException(status_code=404, detail="查询结果不存在")
    
    result = query_results[query_id]
    
    return {
        "query_id": query_id,
        "verification_status": result.verification_status,
        "citations": [
            {
                "article_id": c.article_id if hasattr(c, 'article_id') else str(c),
                "is_verified": c.is_verified if hasattr(c, 'is_verified') else False,
                "original_text": c.original_text if hasattr(c, 'original_text') else ""
            }
            for c in result.citations
        ],
        "issues": result.verification_issues
    }


@app.get("/intent/{intent_type}")
async def get_intent_examples(intent_type: str):
    """
    获取意图类型的示例问题
    
    Args:
        intent_type: 意图类型
        
    Returns:
        示例问题列表
    """
    examples = {
        "law_article": [
            "民法典第143条规定了什么？",
            "合同编第520条内容是什么？",
            "请告诉我第467条的具体内容"
        ],
        "case_query": [
            "有没有类似的案例？",
            "这种情况法院一般怎么判？",
            "能否提供一些相关判例？"
        ],
        "legal_application": [
            "租房纠纷怎么处理？",
            "合同违约应该赔偿多少？",
            "这种情况适用什么法律？"
        ],
        "comparison": [
            "定金和订金有什么区别？",
            "情势变更和不可抗力有何不同？",
            "书面合同和口头合同的法律效力一样吗？"
        ],
        "analysis": [
            "签订房屋买卖合同需要注意哪些法律问题？",
            "网购纠纷如何依法维权？",
            "投资合同中的风险条款有什么法律意义？"
        ],
        "clarification": [
            "什么是格式条款？",
            "这条法律怎么理解？",
            "什么是合同的实质性变更？"
        ]
    }
    
    return {
        "intent_type": intent_type,
        "examples": examples.get(intent_type, [])
    }


# ==================== 启动服务 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
