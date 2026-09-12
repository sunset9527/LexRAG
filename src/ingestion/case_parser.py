"""将年度案例 OCR 页面解析为可追溯的结构化案例。"""

from dataclasses import dataclass, field
import re
from typing import Any


SECTION_PATTERN = re.compile(r"【([^】]+)】")
LEGAL_BASIS_PATTERN = re.compile(r"《[^》]+》第[一二三四五六七八九十百千万0-9]+条")


@dataclass
class ParsedAnnualCase:
    """尚未持久化的案例结构化结果。"""

    title: str | None
    domain: str
    case_cause: str
    key_facts: str
    issues: str | None
    court_reasoning: str | None
    judgment_result: str | None
    judge_commentary: str | None
    legal_basis: list[str] = field(default_factory=list)
    source_start_page: int = 0
    source_end_page: int = 0
    extraction_warnings: list[str] = field(default_factory=list)


class AnnualCaseParser:
    """依靠出版物中的固定中文段落标题提取字段，不生成新事实。"""

    def __init__(self, *, domain: str):
        self._domain = domain

    def parse_case(
        self,
        *,
        sequence_no: int,
        case_cause: str,
        pages: list[dict[str, Any]],
    ) -> ParsedAnnualCase:
        if not pages:
            raise ValueError("案例至少需要一页 OCR 文本")
        content = "\n".join(str(page.get("text", "")) for page in pages).strip()
        title = self._extract_title(content)
        issues = self._section(content, "案件焦点")
        reasoning = self._section(content, "法院裁判要旨") or self._section(content, "裁判理由")
        commentary = self._section(content, "法官后语")
        result = self._judgment_result(content)
        facts = self._facts_before_first_section(content, title)
        warnings = []
        for name, value in (("案件焦点", issues), ("法院裁判要旨/裁判理由", reasoning), ("裁判结果", result)):
            if not value:
                warnings.append(f"未识别{name}")
        if not title:
            warnings.append("未识别案例标题")
        page_numbers = [int(page["page"]) for page in pages]
        return ParsedAnnualCase(
            title=title,
            domain=self._domain,
            case_cause=case_cause,
            key_facts=facts,
            issues=issues,
            court_reasoning=reasoning,
            judgment_result=result,
            judge_commentary=commentary,
            legal_basis=list(dict.fromkeys(LEGAL_BASIS_PATTERN.findall(content))),
            source_start_page=min(page_numbers),
            source_end_page=max(page_numbers),
            extraction_warnings=warnings,
        )

    @staticmethod
    def _extract_title(content: str) -> str | None:
        for line in (line.strip() for line in content.splitlines()):
            if "诉" in line and line.endswith("案") and not line.startswith("【"):
                return line
        return None

    @staticmethod
    def _section(content: str, section_name: str) -> str | None:
        match = re.search(rf"【{re.escape(section_name)}】\s*", content)
        if not match:
            return None
        next_header = SECTION_PATTERN.search(content, match.end())
        value = content[match.end() : next_header.start() if next_header else len(content)].strip()
        if section_name in {"法院裁判要旨", "裁判理由"}:
            value = re.split(r"判决如下[：:]?", value, maxsplit=1)[0].strip()
        return value or None

    @staticmethod
    def _judgment_result(content: str) -> str | None:
        match = re.search(r"判决如下[：:]?\s*", content)
        if not match:
            return None
        next_header = SECTION_PATTERN.search(content, match.end())
        value = content[match.end() : next_header.start() if next_header else len(content)].strip()
        return value or None

    @staticmethod
    def _facts_before_first_section(content: str, title: str | None) -> str:
        first_section = SECTION_PATTERN.search(content)
        facts = content[: first_section.start() if first_section else len(content)].strip()
        if title:
            facts = facts.replace(title, "", 1).strip()
        return facts
