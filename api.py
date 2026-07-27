"""
FastAPI 后端服务 — LexRAG API

提供 RESTful API 接口
v1.7: 新增认证系统、Prompt 管理、数据库、Langfuse 可观测性
"""

# ⚠️ HF_ENDPOINT 必须在所有 import 之前设置，否则 sentence_transformers 会直连 huggingface.co
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from config import settings, get_project_root
from src.utils.embedding_factory import create_embeddings
from src.agent.workflow import LegalRAGWorkflow
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
from src.ingestion.law_parser import LawParser
from src.ingestion.chunker import StructuredLawChunker

# v1.7: 新增模块
from app.db.session import init_db
from app.api.auth import router as auth_router
from app.api.prompts import router as prompts_router
from app.services.langfuse_helper import flush_langfuse
from app.services.prompt_service import seed_default_prompts
from app.models.chat_history import ChatHistory
from app.db.session import SessionLocal

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


# ==================== 全局组件 ====================

components: Dict[str, Any] = {}
query_results: Dict[str, QueryResult] = {}


def initialize_components():
    """初始化组件"""
    global components
    
    try:
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
        
        # 初始化工作流
        workflow = LegalRAGWorkflow(
            intent_router=intent_router,
            law_retriever=law_retriever,
            case_retriever=case_retriever,
            bm25_retriever=bm25_retriever,
            reranker=reranker,
            query_rewriter=query_rewriter,
            context_compressor=context_compressor,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            max_verification_retries=settings.verification_max_retries
        )
        
        components = {
            "workflow": workflow,
            "law_indexer": law_indexer,
            "law_graph": law_graph,
            "intent_router": intent_router,
            "law_retriever": law_retriever,
            "case_retriever": case_retriever,
            "bm25_retriever": bm25_retriever,
            "reranker": reranker,
            "query_rewriter": query_rewriter
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
    version="1.7.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# v1.7: 注册新路由
app.include_router(auth_router)
app.include_router(prompts_router)


# ==================== API端点 ====================

@app.get("/", response_model=Dict[str, str])
async def root():
    """根路径"""
    return {
        "message": "LexRAG 法律智能知识平台 API",
        "version": "1.7.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy" if components else "initializing",
        timestamp=datetime.now().isoformat(),
        version="1.7.0",
        components={
            "workflow": "ready" if components.get("workflow") else "not_ready",
            "law_indexer": "ready" if components.get("law_indexer") else "not_ready",
            "law_graph": "ready" if components.get("law_graph") else "not_ready"
        }
    )


@app.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_model: str | None = Header(None, alias="X-Model"),
    x_base_url: str | None = Header(None, alias="X-Base-URL"),
):
    """
    法律问答接口

    支持通过自定义 Header 传入用户配置：
    - X-API-Key: 用户自己的 LLM API Key
    - X-Base-URL: 用户选择的 API 基础 URL
    - X-Model: 用户选择的模型名称
    """
    if not components.get("workflow"):
        raise HTTPException(status_code=503, detail="系统未初始化")

    try:
        logger.info(f"处理查询: {request.query}")

        # 构建运行时配置（用户设置优先于服务端默认）
        runtime_config = {
            "configurable": {"thread_id": request.session_id or str(uuid.uuid4())},
        }
        if x_api_key:
            runtime_config["user_api_key"] = x_api_key
        if x_base_url:
            runtime_config["user_base_url"] = x_base_url
        if x_model:
            runtime_config["user_model"] = x_model

        # 执行查询
        workflow = components["workflow"]
        result = workflow.query(
            request.query,
            config=runtime_config,
        )

        # 保存结果到内存
        query_id = result.metadata.get("query_id", request.session_id or str(uuid.uuid4()))
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

        # v1.7: 持久化聊天历史
        try:
            if SessionLocal:
                db = SessionLocal()
                try:
                    chat = ChatHistory(
                        user_id=1,  # 默认匿名用户（v1.8 Vue 3 前端接入 auth 后改为真实 user_id）
                        session_id=query_id,
                        question=request.query,
                        answer=result.answer,
                        intent=result.intent,
                        citations=citations_safe,
                        verification_status=result.verification_status,
                        metadata_=result.metadata,
                    )
                    db.add(chat)
                    db.commit()
                finally:
                    db.close()
        except Exception as e:
            logger.warning(f"聊天历史保存失败（非致命）: {e}")

        # 转换为响应格式
        return QueryResponse(
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
async def get_graph():
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

        # 转译为前端 ECharts 格式
        nodes = []
        for n in raw.get("nodes", []):
            in_deg = n.get("citation_count", 0)
            nodes.append({
                "name": n.get("id", n.get("label", "")),
                "symbolSize": max(18, 20 + in_deg * 4),
                "category": 0,
            })
        links = [
            {"source": e["from"], "target": e["to"]}
            for e in raw.get("edges", [])
        ]

        return {
            "statistics": graph.get_statistics(),
            "most_cited": graph.get_most_cited(top_n=10),
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
