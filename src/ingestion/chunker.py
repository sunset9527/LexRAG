"""
法律文档结构化切分器

按法律文档结构切分（编→章→节→条/款/项），不按字符数
保留完整层级元数据
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from .law_parser import LawArticle, LawParser

logger = logging.getLogger(__name__)


@dataclass
class LawChunk:
    """法律文档块"""

    chunk_id: str  # 块ID
    chunk_type: str  # 块类型：article/paragraph/item
    article_id: str  # 所属法条ID
    article_number: str  # 条号
    law_name: str  # 法律名称
    chapter: str  # 所属章
    content: str  # 块内容
    section: str | None = None  # 所属节
    full_article_content: str = ""  # 完整法条内容（用于款/项的上下文）
    effective_date: str | None = None  # 生效日期
    latest_amendment: str | None = None  # 最近修订日期
    version: str = "v1.0"  # 版本标识
    metadata: dict[str, Any] = field(default_factory=dict)  # 其他元数据

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "article_id": self.article_id,
            "article_number": self.article_number,
            "law_name": self.law_name,
            "chapter": self.chapter,
            "section": self.section,
            "content": self.content,
            "full_article_content": self.full_article_content,
            "effective_date": self.effective_date,
            "latest_amendment": self.latest_amendment,
            "version": self.version,
            "metadata": self.metadata,
        }


class StructuredLawChunker:
    """
    法律文档结构化切分器

    按法律文档的固有结构进行切分：
    - 条（Article）：最小检索单位，每条作为一个chunk
    - 款（Paragraph）：如果款有独立检索价值，可单独切分
    - 项（Item）：最小的语义单元

    特点：
    - 不按字符数切分，保持法律条文的完整性
    - 保留层级结构元数据
    - 支持版本追溯
    """

    def __init__(self, version: str = "v1.0"):
        """
        初始化切分器

        Args:
            version: 当前版本标识
        """
        self.version = version
        self.parser = LawParser()
        self.chunks: list[LawChunk] = []
        self.chunk_counter = 0

    def chunk_articles(self, articles: list[LawArticle]) -> list[LawChunk]:
        """
        将法律条文列表切分为chunks

        Args:
            articles: 解析后的法律条文列表

        Returns:
            切分后的chunk列表
        """
        self.chunks = []
        self.chunk_counter = 0

        for article in articles:
            article_chunks = self._chunk_single_article(article)
            self.chunks.extend(article_chunks)

        logger.info(f"切分完成，共生成 {len(self.chunks)} 个chunks")
        return self.chunks

    def chunk_file(self, file_path: str) -> list[LawChunk]:
        """
        直接切分法律文件

        Args:
            file_path: 法律文件路径

        Returns:
            切分后的chunk列表
        """
        articles = self.parser.parse_law_file(file_path)
        return self.chunk_articles(articles)

    def _chunk_single_article(self, article: LawArticle) -> list[LawChunk]:
        """
        切分单个法律条文

        Args:
            article: 法律条文对象

        Returns:
            该条文产生的chunks列表
        """
        chunks = []

        # 1. 条级chunk（完整法条）
        article_chunk = self._create_article_chunk(article)
        chunks.append(article_chunk)

        # 2. 如果有条文正文包含多款，可考虑款级chunk
        if article.content and len(article.paragraphs) > 1:
            # 为每款创建独立chunk（可选，取决于是否需要细粒度检索）
            for idx, paragraph in enumerate(article.paragraphs):
                paragraph_chunk = self._create_paragraph_chunk(article, idx, paragraph)
                chunks.append(paragraph_chunk)

        return chunks

    def _create_article_chunk(self, article: LawArticle) -> LawChunk:
        """
        创建条级chunk

        Args:
            article: 法律条文

        Returns:
            条级chunk
        """
        self.chunk_counter += 1
        chunk_id = f"chunk_{self.version}_{self.chunk_counter:05d}"

        return LawChunk(
            chunk_id=chunk_id,
            chunk_type="article",
            article_id=article.article_id,
            article_number=article.article_number,
            law_name=article.law_name,
            chapter=article.chapter,
            section=article.section,
            content=article.content,
            full_article_content=article.content,
            effective_date=article.effective_date or "2021-01-01",  # 民法典生效日期
            latest_amendment=article.latest_amendment,
            version=self.version,
            metadata={
                "referenced_articles": article.references,
                "paragraph_count": len(article.paragraphs),
                "is_amended": article.is_amended,
            },
        )

    def _create_paragraph_chunk(self, article: LawArticle, idx: int, paragraph: str) -> LawChunk:
        """
        创建款级chunk

        Args:
            article: 法律条文
            idx: 款在条文中的索引
            paragraph: 款的内容

        Returns:
            款级chunk
        """
        self.chunk_counter += 1
        chunk_id = f"chunk_{self.version}_{self.chunk_counter:05d}"

        return LawChunk(
            chunk_id=chunk_id,
            chunk_type="paragraph",
            article_id=article.article_id,
            article_number=article.article_number,
            law_name=article.law_name,
            chapter=article.chapter,
            section=article.section,
            content=paragraph,
            full_article_content=article.content,
            effective_date=article.effective_date or "2021-01-01",
            latest_amendment=article.latest_amendment,
            version=self.version,
            metadata={
                "paragraph_index": idx,
                "parent_article": article.article_id,
                "referenced_articles": article.references,
            },
        )

    def chunk_with_context(
        self, articles: list[LawArticle], context_before: int = 2, context_after: int = 1
    ) -> list[LawChunk]:
        """
        带上下文的切分（增加相邻条文作为上下文）

        Args:
            articles: 法律条文列表
            context_before: 前面保留的条文数
            context_after: 后面保留的条文数

        Returns:
            带上下文的chunks列表
        """
        self.chunks = []
        self.chunk_counter = 0

        # 按条号排序
        sorted_articles = sorted(articles, key=lambda x: int(x.article_number))

        for i, article in enumerate(sorted_articles):
            # 获取上下文
            start_idx = max(0, i - context_before)
            end_idx = min(len(sorted_articles), i + context_after + 1)
            context_articles = sorted_articles[start_idx:end_idx]

            # 构建上下文文本
            context_text = "\n".join(
                [
                    f"{a.article_id}: {a.content}"
                    for a in context_articles
                    if a.article_id != article.article_id
                ]
            )

            self.chunk_counter += 1
            chunk_id = f"chunk_{self.version}_{self.chunk_counter:05d}"

            chunk = self._create_article_chunk(article)
            chunk.chunk_id = chunk_id
            chunk.metadata["context_before"] = context_before
            chunk.metadata["context_after"] = context_after
            chunk.metadata["context_text"] = context_text

            self.chunks.append(chunk)

        return self.chunks

    def get_chunk_by_id(self, chunk_id: str) -> LawChunk | None:
        """根据chunk_id获取chunk"""
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def get_chunks_by_article(self, article_id: str) -> list[LawChunk]:
        """获取指定法条的所有chunks"""
        return [c for c in self.chunks if c.article_id == article_id]

    def get_chunks_by_chapter(self, chapter: str) -> list[LawChunk]:
        """获取指定章节的所有chunks"""
        return [c for c in self.chunks if c.chapter == chapter]

    def export_to_dicts(self) -> list[dict[str, Any]]:
        """导出为字典列表"""
        return [chunk.to_dict() for chunk in self.chunks]

    def get_statistics(self) -> dict[str, Any]:
        """获取切分统计信息"""
        stats = {
            "total_chunks": len(self.chunks),
            "article_chunks": len([c for c in self.chunks if c.chunk_type == "article"]),
            "paragraph_chunks": len([c for c in self.chunks if c.chunk_type == "paragraph"]),
            "unique_articles": len(set(c.article_id for c in self.chunks)),
            "unique_chapters": len(set(c.chapter for c in self.chunks if c.chapter)),
        }
        return stats
