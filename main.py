"""
Streamlit Web界面 — 三栏布局版

对话区 | 检索过程可视化 | 法条溯源面板
"""

import streamlit as st
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from config import settings, get_project_root

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format
)
logger = logging.getLogger(__name__)


def setup_page():
    """设置页面配置"""
    st.set_page_config(
        page_title="法律RAG智能体",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    st.markdown("""
    <style>
    .main-header {
        font-size: 1.8rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .subtitle {
        text-align: center;
        color: gray;
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }
    .step-box {
        background-color: #f8f9fa;
        border-left: 3px solid #1f77b4;
        padding: 0.5rem 0.8rem;
        margin: 0.3rem 0;
        border-radius: 3px;
        font-size: 0.85rem;
    }
    .tool-call-box {
        background-color: #e8f4fd;
        border-left: 3px solid #0d6efd;
        padding: 0.5rem 0.8rem;
        margin: 0.3rem 0;
        border-radius: 3px;
        font-size: 0.85rem;
    }
    .citation-card {
        background-color: #f0f8ff;
        border: 1px solid #d0e7ff;
        border-radius: 6px;
        padding: 0.8rem;
        margin: 0.4rem 0;
    }
    .verified-badge {
        color: #28a745;
        font-weight: bold;
    }
    .unverified-badge {
        color: #ffc107;
        font-weight: bold;
    }
    /* 让三栏间距更合理 */
    [data-testid="column"] {
        padding: 0 0.5rem;
    }
    </style>
    """, unsafe_allow_html=True)


@st.cache_resource
def initialize_components():
    """初始化系统组件"""
    try:
        from src.retrieval.intent_router import IntentRouter
        from src.retrieval.law_retriever import LawRetriever
        from src.retrieval.bm25_retriever import BM25Retriever
        from src.retrieval.reranker import CrossEncoderReranker
        from src.retrieval.query_rewriter import QueryRewriter
        from src.retrieval.context_compressor import ContextCompressor
        from src.ingestion.indexer import LawIndexer
        from src.graph.law_graph import LawGraph
        from src.agent.workflow import LegalRAGWorkflow
        
        # 意图路由器
        intent_router = IntentRouter(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model
        )
        
        # 向量存储
        law_indexer = LawIndexer(
            persist_directory=settings.chroma_persist_directory,
            embedding_model=settings.embedding_model,
            collection_name=settings.law_collection_name
        )
        
        # 法条检索器
        law_retriever = LawRetriever(
            vectorstore=law_indexer.vectorstore,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model
        )
        
        # BM25检索器
        bm25_retriever = None
        if settings.bm25_enabled:
            try:
                bm25_retriever = BM25Retriever()
                # 从向量库加载文档构建BM25索引
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
                        logger.info(f"BM25索引构建完成，{len(bm25_docs)}个文档")
                except Exception as e:
                    logger.warning(f"BM25索引构建失败: {e}")
                    bm25_retriever = None
            except Exception as e:
                logger.warning(f"BM25检索器初始化失败: {e}")
                bm25_retriever = None
        
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
        
        # 知识图谱
        law_graph_path = get_project_root() / settings.law_graph_path
        law_graph = None
        if law_graph_path.exists():
            try:
                law_graph = LawGraph.from_json(str(law_graph_path))
            except Exception as e:
                logger.warning(f"知识图谱加载失败: {e}")
        
        # 工作流
        workflow = LegalRAGWorkflow(
            intent_router=intent_router,
            law_retriever=law_retriever,
            bm25_retriever=bm25_retriever,
            reranker=reranker,
            query_rewriter=query_rewriter,
            context_compressor=context_compressor,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            max_verification_retries=settings.verification_max_retries
        )
        
        return {
            "workflow": workflow,
            "law_indexer": law_indexer,
            "law_graph": law_graph,
            "intent_router": intent_router,
            "law_retriever": law_retriever,
            "bm25_retriever": bm25_retriever,
            "reranker": reranker
        }
    except Exception as e:
        logger.error(f"初始化组件失败: {e}")
        import traceback
        error_detail = traceback.format_exc()
        traceback.print_exc()
        return {"error": str(e), "traceback": error_detail}


def render_chat_message(role: str, content: str):
    """渲染聊天消息"""
    if role == "user":
        st.markdown(f"😀 **你：** {content}")
    else:
        st.markdown(f"🤖 **助手：** {content}")


def render_retrieval_trace(trace: List[Dict[str, Any]]):
    """渲染检索过程追踪"""
    if not trace:
        return
    
    for i, step in enumerate(trace, 1):
        step_type = step.get("step_type", "unknown")
        description = step.get("description", "")
        
        if step_type == "tool_call":
            tool_name = step.get("input", {}).get("name", description)
            st.markdown(f"""
            <div class="tool-call-box">
                <strong>🔧 Step {i}:</strong> {description}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="step-box">
                <strong>Step {i}:</strong> {description}
            </div>
            """, unsafe_allow_html=True)


def render_citations(citations: List[Dict[str, Any]]):
    """渲染法条溯源面板"""
    if not citations:
        return  # 没有引用就不显示任何内容

    for citation in citations:
        article_id = citation.get("article_id", "未知")
        is_verified = citation.get("is_verified", False)
        original_text = citation.get("original_text", citation.get("citation_text", ""))

        # 判断是否未收录
        is_not_found = original_text and "暂未收录" in str(original_text)

        if is_not_found:
            badge = "📭 未收录"
            badge_class = "unverified-badge"
        elif is_verified:
            badge = "✅ 已校验"
            badge_class = "verified-badge"
        else:
            badge = "❓ 待校验"
            badge_class = "unverified-badge"

        with st.container():
            st.markdown(f"""
            <div class="citation-card">
                <strong>{article_id}</strong> <span class="{badge_class}">{badge}</span>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("查看原文", expanded=False):
                if is_not_found:
                    st.info("该法条暂未收录到知识库中，系统仅索引了民法典合同编第463-501条。")
                elif original_text:
                    st.text(str(original_text)[:500])
                else:
                    st.text("暂无原文")


def main():
    """主函数"""
    setup_page()
    
    # 标题
    st.markdown('<h1 class="main-header">⚖️ Agentic RAG 法律问答系统</h1>', unsafe_allow_html=True)
    # st.markdown('<p class="subtitle">DeepSeek + LangGraph ReAct Agent + 民法典 </p>', unsafe_allow_html=True)
    
    # 初始化
    if "components" not in st.session_state:
        with st.spinner("正在初始化系统..."):
            components = initialize_components()
            if components and "error" not in components:
                st.session_state["components"] = components
                st.session_state["initialized"] = True
                st.session_state["chat_history"] = []
            else:
                error_msg = components.get("error", "未知错误") if components else "initialize_components 返回 None"
                error_tb = components.get("traceback", "") if components else ""
                st.error(f"❌ 系统初始化失败\n\n**错误：** {error_msg}")
                if error_tb:
                    with st.expander("查看详细堆栈"):
                        st.code(error_tb)
                st.stop()
    
    # === 对话区 ===
    st.markdown("### 💬 法律咨询对话")

    # 显示聊天历史
    if st.session_state.get("chat_history"):
        for chat in st.session_state.chat_history:
            render_chat_message(chat["role"], chat["content"])

    # 输入区
    st.markdown("---")

    # 示例问题快捷按钮
    example_cols = st.columns(3)
    examples = [
        "合同成立需要满足哪些条件？",
        "格式条款什么情况下无效？",
        "定金和订金有什么区别？"
    ]
    for i, example in enumerate(examples):
        with example_cols[i]:
            if st.button(example, key=f"ex_{i}", use_container_width=True):
                st.session_state["pending_query"] = example

    # 输入框
    query = st.text_input(
        "输入你的法律问题：",
        placeholder="例如：合同成立需要满足哪些条件？",
        key="query_input",
        value=st.session_state.get("pending_query", "")
    )

    if st.button("🔍 提问", type="primary", use_container_width=True) or st.session_state.get("pending_query"):
        if query or st.session_state.get("pending_query"):
            actual_query = query or st.session_state.get("pending_query", "")
            st.session_state["pending_query"] = ""

            # 添加用户消息
            st.session_state.chat_history.append({"role": "user", "content": actual_query})

            # 执行查询
            components = st.session_state.get("components", {})
            workflow = components.get("workflow")

            if workflow:
                with st.spinner("🤖 Agent正在思考..."):
                    try:
                        result = workflow.query(actual_query)
                        result_dict = result.to_dict()

                        # 添加助手消息
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": result_dict.get("answer", ""),
                        })
                    except Exception as e:
                        st.error(f"处理查询时发生错误: {str(e)}")
                        logger.error(f"查询失败: {e}")
            else:
                st.error("系统未初始化")

            st.rerun()


if __name__ == "__main__":
    main()
