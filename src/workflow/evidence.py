"""v2.1 的证据账本与确定性法条引用校验。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass
class EvidenceItem:
    """一次查询中可供回答引用的最小证据单元。"""

    source_id: str
    source_type: str
    knowledge_base_slug: str
    law_name: str
    article_id: str
    content: str
    score: float
    retrieval_path: str
    source_position: str | None = None
    version_id: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    retrieval_paths: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        if self.retrieval_path:
            self.retrieval_paths.add(self.retrieval_path)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source_type, self.knowledge_base_slug, self.source_id)

    @property
    def normalized_article_id(self) -> str:
        return normalize_article_id(self.article_id)

    def is_citable_statute(self) -> bool:
        return bool(
            self.source_type == "statute"
            and self.source_id.strip()
            and self.knowledge_base_slug.strip()
            and self.law_name.strip()
            and self.normalized_article_id
            and self.content.strip()
        )


class EvidenceLedger:
    """按来源和知识库隔离、去重本次查询中的证据。"""

    def __init__(self, items: Iterable[EvidenceItem] | None = None) -> None:
        self._items: dict[tuple[str, str, str], EvidenceItem] = {}
        self.rejected_count = 0
        for item in items or []:
            self.add(item)

    @property
    def items(self) -> list[EvidenceItem]:
        return list(self._items.values())

    def add(self, item: EvidenceItem) -> bool:
        if item.source_type == "statute" and not item.is_citable_statute():
            self.rejected_count += 1
            return False

        existing = self._items.get(item.key)
        if existing is None:
            self._items[item.key] = item
            return True

        existing.retrieval_paths.update(item.retrieval_paths)
        if item.score > existing.score:
            existing.score = item.score
            existing.content = item.content
            existing.law_name = item.law_name
            existing.article_id = item.article_id
            existing.source_position = item.source_position
        return True

    def statutes_for(self, knowledge_base_slug: str) -> list[EvidenceItem]:
        return [
            item
            for item in self.items
            if item.source_type == "statute"
            and item.knowledge_base_slug == knowledge_base_slug
            and item.is_citable_statute()
        ]


@dataclass
class VerifiedCitation:
    law_name: str
    article_id: str
    citation_text: str
    is_verified: bool
    original_text: str = ""
    knowledge_base_slug: str | None = None
    version_id: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_url: str | None = None
    content_hash: str | None = None


@dataclass
class CitationVerificationResult:
    status: str
    citations: list[VerifiedCitation]
    issues: list[str]


class CitationVerifier:
    """不调用模型，只允许引用当前证据账本中的法条。"""

    _CITATION_PATTERN = re.compile(
        r"【(?P<law_name>[^【】]*?)第(?P<article_id>[零一二三四五六七八九十百千\d]+)(?:条之(?P<subsection>[零一二三四五六七八九十百千\d]+))?条?】"
    )

    def verify(
        self,
        answer: str,
        ledger: EvidenceLedger,
        *,
        knowledge_base_slug: str | None = None,
        knowledge_base_slugs: Iterable[str] | None = None,
    ) -> CitationVerificationResult:
        citations = self._extract(answer)
        if not citations:
            return CitationVerificationResult(
                status="fail",
                citations=[],
                issues=["回答中未包含可校验的法条引用"],
            )

        selected_slugs = {slug for slug in (knowledge_base_slugs or []) if slug}
        if knowledge_base_slug:
            selected_slugs.add(knowledge_base_slug)
        allowed = [
            item
            for slug in selected_slugs
            for item in ledger.statutes_for(slug)
        ]
        issues: list[str] = []
        for citation in citations:
            same_article = [
                item for item in allowed if item.normalized_article_id == citation.article_id
            ]
            exact_items = [item for item in same_article if item.law_name == citation.law_name]
            if exact_items:
                source = max(exact_items, key=lambda item: item.score)
                citation.is_verified = True
                citation.original_text = source.content
                citation.knowledge_base_slug = source.knowledge_base_slug
                citation.version_id = source.version_id
                citation.effective_from = source.effective_from
                citation.effective_to = source.effective_to
                citation.source_url = source.source_url
                citation.content_hash = source.content_hash
            elif same_article:
                issues.append(f"引用法律名称不匹配：{citation.citation_text}")
            else:
                issues.append(f"引用不在本次证据账本中：{citation.citation_text}")

        return CitationVerificationResult(
            status="pass" if not issues else "fail",
            citations=citations,
            issues=issues,
        )

    def _extract(self, answer: str) -> list[VerifiedCitation]:
        citations: list[VerifiedCitation] = []
        seen: set[tuple[str, str]] = set()
        for match in self._CITATION_PATTERN.finditer(answer):
            raw_article_id = match.group("article_id")
            subsection = match.group("subsection")
            if subsection:
                raw_article_id = f"{raw_article_id}-{subsection}"
            article_id = normalize_article_id(raw_article_id)
            law_name = match.group("law_name").strip()
            key = (law_name, article_id)
            if not article_id or key in seen:
                continue
            seen.add(key)
            citations.append(
                VerifiedCitation(
                    law_name=law_name,
                    article_id=article_id,
                    citation_text=match.group(0),
                    is_verified=False,
                )
            )
        return citations


def normalize_article_id(value: str) -> str:
    """将阿拉伯或常见中文条号规范化为阿拉伯数字字符串。"""
    value = value.strip().replace("第", "")
    subsection_match = re.fullmatch(r"(.+?)(?:条之|-)([零一二三四五六七八九十百千\d]+)条?", value)
    if subsection_match:
        base = normalize_article_id(subsection_match.group(1))
        subsection = normalize_article_id(subsection_match.group(2))
        return f"{base}-{subsection}" if base and subsection else ""
    value = value.replace("条", "")
    if value.isdigit():
        return str(int(value))

    digit_values = {
        "零": 0,
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
    unit_values = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for char in value:
        if char in digit_values:
            current = digit_values[char]
        elif char in unit_values:
            total += (current or 1) * unit_values[char]
            current = 0
        else:
            return ""
    return str(total + current) if total + current else ""
