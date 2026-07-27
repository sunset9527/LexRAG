"""上下文压缩"""
import logging
from typing import List, Dict, Any

# v1.7: Langfuse 可观测工厂
from app.services.langfuse_helper import create_llm

logger = logging.getLogger(__name__)

class ContextCompressor:
    """
    上下文压缩器
    
    对检索到的长法条全文进行压缩，保留与查询最相关的内容
    """
    
    COMPRESS_PROMPT = """请从以下法条内容中，提取与问题最相关的部分。

问题：{query}

法条内容：
{document}

要求：
1. 只保留与问题直接相关的段落和句子
2. 保留法条编号
3. 不要改写内容，只做删减
4. 压缩后的内容不超过{max_tokens}个字符

压缩后的内容："""
    
    def __init__(
        self,
        api_key=None,
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        max_tokens_per_doc: int = 500
    ):
        self.llm = create_llm(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
        )
        self.max_tokens_per_doc = max_tokens_per_doc
    
    def compress(self, query: str, documents: List[Dict[str, Any]], content_key: str = "content") -> List[Dict[str, Any]]:
        """压缩文档列表"""
        compressed = []
        for doc in documents:
            content = doc.get(content_key, "")
            if len(content) <= self.max_tokens_per_doc:
                compressed.append(doc)
                continue
            try:
                prompt = self.COMPRESS_PROMPT.format(
                    query=query,
                    document=content,
                    max_tokens=self.max_tokens_per_doc
                )
                response = self.llm.invoke(prompt)
                compressed_doc = doc.copy()
                compressed_doc[content_key] = response.content
                compressed_doc["is_compressed"] = True
                compressed.append(compressed_doc)
            except Exception as e:
                logger.error(f"压缩文档失败: {e}")
                compressed.append(doc)
        return compressed
    
    def compress_to_context(self, query: str, documents: List[Dict[str, Any]], max_total_tokens: int = 4000) -> str:
        """将文档列表压缩为一段上下文文本"""
        # 先简单按长度截取
        context_parts = []
        total_length = 0
        for doc in documents:
            content = doc.get("content", "")
            article_id = doc.get("doc_id", doc.get("article_id", ""))
            part = f"【{article_id}】\n{content}\n"
            if total_length + len(part) > max_total_tokens:
                # 截断
                remaining = max_total_tokens - total_length
                if remaining > 100:
                    part = part[:remaining] + "..."
                    context_parts.append(part)
                break
            context_parts.append(part)
            total_length += len(part)
        return "\n".join(context_parts)
