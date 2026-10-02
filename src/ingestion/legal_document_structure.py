"""合同与判决书的规则优先、可回指结构化解析。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

PageText = tuple[int, str]


@dataclass
class StructuredDocument:
    """结构化内容及其输入页面，用于后续持久化和人工复核。"""

    document_type: str
    content: dict
    pages: list[PageText]
    parser_version: str = "v2.3.2-rule"


_CLAUSE_START = re.compile(
    r"(?m)^("
    r"第[一二三四五六七八九十百千万零〇0-9]+条(?:之[一二三四五六七八九十]+)?"
    r"|(?:\d+\.)+\d+"
    r")\s*([^\n]*)"
)
_LEGAL_BASIS = re.compile(
    r"《[^》]+》第[一二三四五六七八九十百千万零〇0-9]+条(?:之[一二三四五六七八九十]+)?"
)


def structure_document(pages: list[PageText]) -> StructuredDocument:
    """按明确的文本锚点识别合同、判决书或通用文档。"""
    normalized_pages = [(page_number, text.strip()) for page_number, text in pages if text.strip()]
    full_text = "\n".join(text for _, text in normalized_pages)
    if "判决书" in full_text or ("本院认为" in full_text and "判决如下" in full_text):
        return StructuredDocument("judgment", _parse_judgment(normalized_pages), normalized_pages)
    has_contract_parties = "甲方" in full_text and "乙方" in full_text
    if _CLAUSE_START.search(full_text) and ("合同" in full_text or has_contract_parties):
        return StructuredDocument("contract", _parse_contract(normalized_pages), normalized_pages)
    return StructuredDocument("general", {}, normalized_pages)


def apply_verified_supplement(
    parsed: StructuredDocument, candidates: Iterable[dict[str, Any]]
) -> StructuredDocument:
    """仅合并能逐字回指输入页面、且不覆盖规则结果的补充字段。"""
    content = dict(parsed.content)
    page_texts = dict(parsed.pages)
    accepted = False
    for candidate in candidates:
        field = candidate.get("field")
        value = candidate.get("value")
        page_number = candidate.get("page_number")
        evidence_text = candidate.get("evidence_text")
        if (
            not isinstance(field, str)
            or field not in content
            or content[field] is not None
            or not isinstance(value, str)
            or not value.strip()
            or not isinstance(page_number, int)
            or not isinstance(evidence_text, str)
            or not evidence_text.strip()
        ):
            continue
        page_text = page_texts.get(page_number)
        if page_text is None or evidence_text not in page_text or value not in evidence_text:
            continue
        field_result: dict[str, Any] = {
            "value": value.strip(),
            "page_number": page_number,
            "evidence_text": evidence_text.strip(),
            "extraction_method": "llm_verified",
        }
        confidence = candidate.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            field_result["confidence"] = float(confidence)
        content[field] = field_result
        accepted = True
    if not accepted:
        return parsed
    return StructuredDocument(
        document_type=parsed.document_type,
        content=content,
        pages=parsed.pages,
        parser_version=f"{parsed.parser_version}+llm-verified",
    )


def _parse_contract(pages: list[PageText]) -> dict:
    clauses = _split_clauses(pages)
    content = {key: None for key in (
        "parties",
        "subject",
        "remuneration",
        "performance",
        "breach",
        "exemption",
        "dispute_resolution",
        "jurisdiction",
        "term",
    )}
    content["parties"] = _contract_parties(pages)
    content["clauses"] = [
        {
            "number": clause["number"],
            "title": clause["title"],
            "page_number": clause["page_number"],
            "evidence_text": clause["text"],
            "extraction_method": "rule",
        }
        for clause in clauses
    ]
    keyword_mapping = {
        "parties": ("当事人", "甲方", "乙方"),
        "subject": ("工作内容", "服务内容", "岗位", "标的"),
        "remuneration": ("劳动报酬", "工资", "价款"),
        "performance": ("履行", "交付"),
        "breach": ("违约",),
        "exemption": ("免责", "免除责任"),
        "dispute_resolution": ("争议", "管辖"),
        "term": ("期限", "有效期"),
    }
    for field, keywords in keyword_mapping.items():
        if content[field] is not None:
            continue
        clause = next(
            (
                item
                for item in clauses
                if any(keyword in f"{item['title']}\n{item['text']}" for keyword in keywords)
            ),
            None,
        )
        if clause is not None:
            content[field] = _field(clause["text"], clause["page_number"])
    dispute = content["dispute_resolution"]
    if dispute is not None:
        court = re.search(r"(?:向|由)([^。\n]*?人民法院)", dispute["value"])
        if court is not None:
            content["jurisdiction"] = _field(court.group(1), dispute["page_number"])
    return content


def _parse_judgment(pages: list[PageText]) -> dict:
    content = {
        "parties": _joined_party_field(pages),
        "case_cause": _anchored_field(pages, ("案由",), trim_terminal_punctuation=True),
        "claims": _anchored_field(pages, ("原告诉称", "原告主张", "诉称")),
        "facts": _anchored_field(pages, ("本院查明",)),
        "court_reasoning": _anchored_field(pages, ("本院认为",)),
        "judgment_result": _anchored_field(pages, ("判决如下",)),
        "legal_basis": [],
    }
    for page_number, text in pages:
        for basis in _LEGAL_BASIS.findall(text):
            content["legal_basis"].append(_field(basis, page_number))
    return content


def _split_clauses(pages: list[PageText]) -> list[dict]:
    clauses: list[dict] = []
    for page_number, text in pages:
        matches = list(_CLAUSE_START.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            clause_text = text[match.end() : end].strip()
            clauses.append(
                {
                    "number": match.group(1),
                    "title": match.group(2).strip(),
                    "text": clause_text,
                    "page_number": page_number,
                }
            )
    return clauses


def _joined_party_field(pages: list[PageText]) -> dict | None:
    for page_number, text in pages:
        lines = [line.strip() for line in text.splitlines()]
        parties = [line for line in lines if re.match(r"^(原告|被告)[：:]", line)]
        if parties:
            return _field("\n".join(parties), page_number)
    return None


def _contract_parties(pages: list[PageText]) -> dict | None:
    """合同当事人可能出现在首个编号条款之前，不能只在条款正文查找。"""
    for page_number, text in pages:
        lines = [line.strip() for line in text.splitlines()]
        parties = [line for line in lines if re.match(r"^(甲方|乙方)[：:]", line)]
        if parties:
            return _field("\n".join(parties), page_number)
    return None


def _anchored_field(
    pages: list[PageText], anchors: tuple[str, ...], *, trim_terminal_punctuation: bool = False
) -> dict | None:
    for page_number, text in pages:
        for line in text.splitlines():
            cleaned = line.strip()
            for anchor in anchors:
                match = re.search(rf"{re.escape(anchor)}[：:]?\s*(.*)", cleaned)
                if match is not None and match.group(1).strip():
                    value = match.group(1).strip()
                    if trim_terminal_punctuation:
                        value = value.rstrip("。；;")
                    return _field(value, page_number)
    return None


def _field(value: str, page_number: int) -> dict:
    return {
        "value": value.strip(),
        "page_number": page_number,
        "evidence_text": value.strip(),
        "extraction_method": "rule",
    }
