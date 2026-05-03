"""
法律RAG Agent工具集

4个面向法律场景的LangChain Tool，供ReAct Agent自主决策调用
"""

import logging
import json
from typing import Optional, List, Dict, Any

from langchain.tools import tool
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# 工具之间共享的检索器引用（在init_tools中设置）
_retriever_registry: Dict[str, Any] = {}


def init_tools(
    law_retriever=None,
    case_retriever=None,
    bm25_retriever=None,
    graph_retriever=None,
    reranker=None,
    query_rewriter=None,
    context_compressor=None,
    api_key: Optional[str] = None,
    base_url: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-chat"
):
    """
    初始化工具注册表
    
    在应用启动时调用，将检索器实例注入到工具模块
    """
    _retriever_registry["law_retriever"] = law_retriever
    _retriever_registry["case_retriever"] = case_retriever
    _retriever_registry["bm25_retriever"] = bm25_retriever
    _retriever_registry["graph_retriever"] = graph_retriever
    _retriever_registry["reranker"] = reranker
    _retriever_registry["query_rewriter"] = query_rewriter
    _retriever_registry["context_compressor"] = context_compressor
    _retriever_registry["llm"] = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.0,
        request_timeout=30,
        max_retries=1
    )


@tool
def search_statute(query: str) -> str:
    """检索民法典条文。输入法律问题描述，返回相关法条原文。用于查找与法律问题相关的法条。"""
    law_retriever = _retriever_registry.get("law_retriever")
    bm25_retriever = _retriever_registry.get("bm25_retriever")
    reranker = _retriever_registry.get("reranker")
    
    if not law_retriever:
        return "错误：法条检索器未初始化"
    
    try:
        # 向量检索
        law_results = law_retriever.retrieve(query, top_k=10)
        
        # BM25检索（如果可用）
        bm25_results = []
        if bm25_retriever:
            from src.retrieval.fusion import reciprocal_rank_fusion
            # 将law_results转为统一格式
            vector_docs = [
                {
                    "doc_id": r.article_id,
                    "content": r.full_content or r.content,
                    "score": float(r.score) if r.score else 0.0,
                    "metadata": r.to_dict()
                }
                for r in law_results
            ]
            
            # BM25检索
            bm25_raw = bm25_retriever.retrieve(query, top_k=10)
            bm25_docs = [
                {
                    "doc_id": r.doc_id,
                    "content": r.content,
                    "score": r.score,
                    "metadata": r.metadata
                }
                for r in bm25_raw
            ]
            
            # RRF融合
            fused = reciprocal_rank_fusion([vector_docs, bm25_docs], k=60)
            
            # 转换为文档列表供reranker
            documents = [
                {"doc_id": f.doc_id, "content": f.content, "score": f.score, "metadata": f.metadata}
                for f in fused[:15]
            ]
        else:
            documents = [
                {"doc_id": r.article_id, "content": r.full_content or r.content, "score": float(r.score) if r.score else 0.0, "metadata": r.to_dict()}
                for r in law_results
            ]
        
        # Reranker精排（如果可用）
        if reranker:
            reranked = reranker.rerank(query, documents, top_k=5)
            results_text = []
            for r in reranked:
                results_text.append(f"【{r.doc_id}】(相关度: {r.score:.3f})\n{r.content}")
            return "\n\n".join(results_text)
        else:
            results_text = []
            for doc in documents[:5]:
                results_text.append(f"【{doc['doc_id']}】\n{doc['content']}")
            return "\n\n".join(results_text)
            
    except Exception as e:
        logger.error(f"法条检索失败: {e}")
        return f"法条检索失败: {str(e)}"


@tool
def search_case(query: str) -> str:
    """检索类似判例。输入案情描述，返回相关判例和裁判要旨。用于查找与当前案情相似的已有判决案例。"""
    case_retriever = _retriever_registry.get("case_retriever")
    
    if not case_retriever:
        return "判例检索器未初始化，暂无法提供判例参考。请基于法条分析回答。"
    
    try:
        results = case_retriever.retrieve(query, top_k=3)
        if not results:
            return "未找到相关判例。"
        
        case_texts = []
        for r in results:
            case_texts.append(
                f"【{r.case_name}】\n"
                f"案号: {r.case_number}\n"
                f"法院: {r.court_level}\n"
                f"裁判要旨: {r.judgment_result}\n"
                f"法律依据: {', '.join(r.legal_basis) if r.legal_basis else '无'}"
            )
        return "\n\n".join(case_texts)
    except Exception as e:
        logger.error(f"判例检索失败: {e}")
        return f"判例检索失败: {str(e)}"


@tool
def lookup_article(article_id: str) -> str:
    """精确查阅法条全文。输入法条编号如'第712条'或'712'，返回完整条款内容。用于确认或查看某个具体法条的完整原文。"""
    law_retriever = _retriever_registry.get("law_retriever")
    
    if not law_retriever:
        return "错误：法条检索器未初始化"
    
    try:
        # 提取数字
        import re
        match = re.search(r'第?(\d+)条?', article_id)
        if match:
            article_num = match.group(1)
        else:
            article_num = article_id
        
        result = law_retriever.retrieve_by_article_number(article_num)
        if result:
            return f"【{result.article_id}】\n{result.full_content}"
        else:
            return f"未找到法条：第{article_num}条"
    except Exception as e:
        logger.error(f"法条查阅失败: {e}")
        return f"法条查阅失败: {str(e)}"


@tool
def analyze_legal_relation(case_description: str) -> str:
    """分析法律关系。输入案情描述，输出法律主体/客体/权利义务分析。用于梳理复杂案情中的法律关系。"""
    llm = _retriever_registry.get("llm")
    
    if not llm:
        return "错误：LLM未初始化"
    
    prompt = f"""你是一个法律专家，请分析以下案情中的法律关系。

案情描述：{case_description}

请从以下维度分析：
1. 法律主体：涉及哪些主体
2. 法律客体：争议的客体是什么
3. 权利义务：各主体之间的权利义务关系
4. 请求权基础：可能适用的法律依据
5. 法律关系类型（合同/侵权/物权等）

请简洁分析，每个维度不超过2-3句话。"""
    
    try:
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        logger.error(f"法律关系分析失败: {e}")
        return f"法律关系分析失败: {str(e)}"


def get_all_tools() -> list:
    """获取所有工具列表，供Agent绑定"""
    return [search_statute, search_case, lookup_article, analyze_legal_relation]
