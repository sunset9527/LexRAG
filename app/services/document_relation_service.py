"""跨文档关联的证据化、知识库隔离服务。"""

import logging
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_job import DocumentJob
from app.models.document_page import DocumentPage
from app.models.document_relation import DocumentRelation

logger = logging.getLogger(__name__)
_ARTICLE_REFERENCE = re.compile(
    r"《(?P<law_name>[^》]+)》第(?P<article>[0-9一二三四五六七八九十百千万零〇]+)条"
)
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


class DocumentRelationService:
    """创建可解释关联，不接受跨库或缺少来源原文的候选。"""

    engine_version = "v2.3.3-rule"
    created_by = "v2.3.3-system"

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        law_lookup: Callable[[str, str], list[dict[str, Any]]] | None = None,
        semantic_candidate_provider: Callable[
            [DocumentJob, list[tuple[int, str]]], list[dict[str, Any]]
        ]
        | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._law_lookup = law_lookup
        self._semantic_candidate_provider = semantic_candidate_provider

    def rebuild(self, document_id: str) -> list[dict[str, Any]]:
        """重新建立当前文档的系统关联；相同输入保持一组稳定边。"""
        with self._session_factory() as session:
            source = self._get_document(session, document_id)
            pages = session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            ).all()
            page_texts = [(page.page_number, page.raw_text) for page in pages]
            relations = self._exact_law_relations(page_texts)
            relations.extend(self._semantic_relations(session, source, page_texts))
            unique_relations = self._deduplicate(relations)

            session.execute(
                delete(DocumentRelation).where(
                    DocumentRelation.source_document_id == document_id,
                    DocumentRelation.created_by == self.created_by,
                )
            )
            stored = [
                DocumentRelation(
                    source_document_id=document_id,
                    source_locator=item["source_locator"],
                    target_type=item["target_type"],
                    target_id=item["target_id"],
                    relation_type=item["relation_type"],
                    law_article=item.get("law_article"),
                    similarity=item.get("similarity"),
                    evidence_text=item.get("evidence_text"),
                    created_by=self.created_by,
                    engine_version=self.engine_version,
                )
                for item in unique_relations
            ]
            session.add_all(stored)
            session.commit()
            return [self._serialize(item) for item in stored]

    def _exact_law_relations(self, pages: list[tuple[int, str]]) -> list[dict[str, Any]]:
        if self._law_lookup is None:
            return []
        relations: list[dict[str, Any]] = []
        for page_number, text in pages:
            for match in _ARTICLE_REFERENCE.finditer(text):
                law_name = match.group("law_name")
                article_number = _normalize_article_number(match.group("article"))
                evidence_text = match.group(0)
                try:
                    targets = self._law_lookup(law_name, article_number)
                except Exception:
                    logger.exception("法条精确关联查询失败: %s 第%s条", law_name, article_number)
                    continue
                for target in targets:
                    target_id = target.get("target_id")
                    if not isinstance(target_id, str) or not target_id:
                        continue
                    relations.append(
                        {
                            "source_locator": f"page:{page_number}",
                            "target_type": str(target.get("target_type", "law_article")),
                            "target_id": target_id,
                            "relation_type": "exact_law_citation",
                            "law_article": f"{law_name}第{article_number}条",
                            "similarity": None,
                            "evidence_text": evidence_text,
                        }
                    )
        return relations

    def _semantic_relations(
        self,
        session: Session,
        source: DocumentJob,
        pages: list[tuple[int, str]],
    ) -> list[dict[str, Any]]:
        if self._semantic_candidate_provider is None:
            return []
        try:
            candidates = self._semantic_candidate_provider(source, pages)
        except Exception:
            logger.exception("语义关联候选生成失败: %s", source.id)
            return []
        page_text_by_number = dict(pages)
        relations: list[dict[str, Any]] = []
        for candidate in candidates:
            target_id = candidate.get("target_document_id")
            page_number = candidate.get("source_page_number")
            evidence_text = candidate.get("evidence_text")
            similarity = candidate.get("similarity")
            if (
                not isinstance(target_id, str)
                or target_id == source.id
                or not isinstance(page_number, int)
                or not isinstance(evidence_text, str)
                or not evidence_text.strip()
                or not isinstance(similarity, (int, float))
                or isinstance(similarity, bool)
                or not 0 <= float(similarity) <= 1
            ):
                continue
            source_text = page_text_by_number.get(page_number)
            if source_text is None or evidence_text not in source_text:
                continue
            target = session.get(DocumentJob, target_id)
            if target is None or target.knowledge_base_slug != source.knowledge_base_slug:
                continue
            relations.append(
                {
                    "source_locator": f"page:{page_number}",
                    "target_type": "document",
                    "target_id": target_id,
                    "relation_type": "semantic_candidate",
                    "law_article": None,
                    "similarity": float(similarity),
                    "evidence_text": evidence_text,
                }
            )
        return relations

    @staticmethod
    def _deduplicate(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for relation in relations:
            key = (
                relation["source_locator"],
                relation["target_type"],
                relation["target_id"],
                relation["relation_type"],
            )
            unique.setdefault(key, relation)
        return list(unique.values())

    @staticmethod
    def _get_document(session: Session, document_id: str) -> DocumentJob:
        document = session.get(DocumentJob, document_id)
        if document is None:
            raise ValueError(f"文档任务不存在: {document_id}")
        return document

    @staticmethod
    def _serialize(relation: DocumentRelation) -> dict[str, Any]:
        return {
            "source_locator": relation.source_locator,
            "target_type": relation.target_type,
            "target_id": relation.target_id,
            "relation_type": relation.relation_type,
            "law_article": relation.law_article,
            "similarity": relation.similarity,
            "evidence_text": relation.evidence_text,
            "created_by": relation.created_by,
            "engine_version": relation.engine_version,
        }


def _normalize_article_number(value: str) -> str:
    """将常见中文数字条号规范为索引使用的阿拉伯数字。"""
    if value.isdigit():
        return value
    total = 0
    current = 0
    for character in value:
        if character in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[character]
            continue
        unit = _CHINESE_UNITS.get(character)
        if unit is None:
            return value
        if current == 0:
            current = 1
        total += current * unit
        current = 0
    return str(total + current)
