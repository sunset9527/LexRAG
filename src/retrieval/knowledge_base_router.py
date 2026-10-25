"""阶段 5 的可审计知识库路由。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeBaseRouteCandidate:
    slug: str
    confidence: float
    reason_code: str


@dataclass(frozen=True)
class KnowledgeBaseRouteDecision:
    mode: str
    candidates: list[KnowledgeBaseRouteCandidate]
    selected_slugs: list[str]
    requires_clarification: bool = False


class KnowledgeBaseRouter:
    """基于法律名称和领域术语选择已授权的法规知识库。"""

    _RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
        ("labor-contract-law", ("劳动合同", "解除劳动", "经济补偿", "试用期", "竞业限制"), 0.9),
        ("labor-law", ("用人单位", "劳动者", "工资", "工时", "休息休假", "劳动争议"), 0.8),
        ("company-law", ("公司", "股东", "董事", "监事", "法定代表人", "注册资本"), 0.8),
        ("criminal-law", ("刑法", "犯罪", "诈骗", "盗窃", "刑事", "判刑"), 0.9),
        ("patent-law", ("专利", "发明", "实用新型", "外观设计"), 0.9),
        ("trademark-law", ("商标", "注册商标", "商标权"), 0.9),
        ("copyright-law", ("著作权", "版权", "作品", "侵权复制"), 0.9),
        ("civil-code", ("民法典", "合同", "买卖", "违约", "侵权", "物权", "婚姻", "继承"), 0.8),
    )

    _CIVIL_COMPANION_SLUGS = frozenset(
        {"company-law", "patent-law", "trademark-law", "copyright-law"}
    )

    def __init__(self, *, max_candidates: int = 3, minimum_confidence: float = 0.7) -> None:
        self.max_candidates = max_candidates
        self.minimum_confidence = minimum_confidence

    def route(
        self,
        question: str,
        available_knowledge_bases: Iterable[dict[str, Any]],
        *,
        explicit_slugs: Iterable[str] | None = None,
    ) -> KnowledgeBaseRouteDecision:
        available = {
            str(item.get("slug", "")): item
            for item in available_knowledge_bases
            if str(item.get("slug", ""))
        }
        explicit = self._unique(explicit_slugs or [])
        if explicit:
            candidates = [
                KnowledgeBaseRouteCandidate(
                    slug=slug, confidence=1.0, reason_code="explicit_selection"
                )
                for slug in explicit
                if slug in available
            ]
            return KnowledgeBaseRouteDecision(
                mode="explicit",
                candidates=candidates,
                selected_slugs=[item.slug for item in candidates],
            )

        normalized = question.lower()
        matched: list[KnowledgeBaseRouteCandidate] = []
        for slug, keywords, confidence in self._RULES:
            if slug not in available or not any(keyword in normalized for keyword in keywords):
                continue
            matched.append(
                KnowledgeBaseRouteCandidate(
                    slug=slug, confidence=confidence, reason_code="domain_terms"
                )
            )

        matched = self._prioritize_specialist_laws(matched, available)
        matched.sort(key=lambda item: -item.confidence)
        candidates = matched[: self.max_candidates]
        selected = [item.slug for item in candidates if item.confidence >= self.minimum_confidence]
        if not selected:
            if not candidates:
                candidates = [
                    KnowledgeBaseRouteCandidate(
                        slug=slug,
                        confidence=0.0,
                        reason_code="clarification_required",
                    )
                    for slug in sorted(available)[: self.max_candidates]
                ]
            return KnowledgeBaseRouteDecision(
                mode="clarification",
                candidates=candidates,
                selected_slugs=[],
                requires_clarification=True,
            )
        return KnowledgeBaseRouteDecision(
            mode="automatic", candidates=candidates, selected_slugs=selected
        )

    def _prioritize_specialist_laws(
        self,
        candidates: list[KnowledgeBaseRouteCandidate],
        available: dict[str, dict[str, Any]],
    ) -> list[KnowledgeBaseRouteCandidate]:
        selected = {item.slug for item in candidates}
        labor_slugs = {"labor-law", "labor-contract-law"}
        if selected.intersection(labor_slugs) or "criminal-law" in selected:
            return [item for item in candidates if item.slug != "civil-code"]

        if selected.intersection(self._CIVIL_COMPANION_SLUGS) and "civil-code" in available:
            candidates = [item for item in candidates if item.slug != "civil-code"]
            candidates.append(
                KnowledgeBaseRouteCandidate(
                    slug="civil-code", confidence=0.75, reason_code="civil_law_companion"
                )
            )
        return candidates

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = str(value).strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result
