"""Stage 4 本地法规原件的候选版本识别。

本模块只接受明确登记过的 DOCX 文件名。它提取正文并计算原件、正文双哈希，
但不会仅凭文件名把用户提供材料标记为权威或可查询版本。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from src.ingestion.document_parser import parse_document

SOURCE_STATUS_CURRENT = "CURRENT"
SOURCE_STATUS_HISTORICAL = "HISTORICAL"
SOURCE_STATUS_PUBLISHED_NOT_EFFECTIVE = "PUBLISHED_NOT_EFFECTIVE"
SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT = "SUPPLEMENTAL_AMENDMENT"


class StatuteSourceIntakeError(ValueError):
    """A local source file cannot safely enter the Stage 4 candidate catalogue."""


@dataclass(frozen=True)
class Stage4SourceSpec:
    filename_stem: str
    law_slug: str
    law_name: str
    version_id: str
    promulgated_on: date
    effective_from: date
    source_status: str
    document_type: str = "STATUTE"


@dataclass(frozen=True)
class Stage4SourceCandidate:
    source_path: Path
    law_slug: str
    law_name: str
    version_id: str
    promulgated_on: date
    effective_from: date
    source_status: str
    raw_sha256: str
    content_sha256: str
    content: str
    document_type: str = "STATUTE"
    parser_version: str = "docx-v1"
    authority_status: str = "PENDING_REVIEW"


@dataclass(frozen=True)
class Stage4SourceScan:
    """Known DOCX candidates plus files intentionally outside this Stage 4 scope."""

    candidates: tuple[Stage4SourceCandidate, ...]
    skipped_files: tuple[Path, ...]


_SPECS: tuple[Stage4SourceSpec, ...] = (
    Stage4SourceSpec(
        "中华人民共和国民法典_20200528",
        "civil-code",
        "中华人民共和国民法典",
        "civil-code@2020-05-28",
        date(2020, 5, 28),
        date(2021, 1, 1),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国劳动法_20090827",
        "labor-law",
        "中华人民共和国劳动法",
        "labor-law@2009-08-27",
        date(2009, 8, 27),
        date(1995, 1, 1),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国劳动法_20181229",
        "labor-law",
        "中华人民共和国劳动法",
        "labor-law@2018-12-29",
        date(2018, 12, 29),
        date(2018, 12, 29),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国劳动合同法_20121228",
        "labor-contract-law",
        "中华人民共和国劳动合同法",
        "labor-contract-law@2012-12-28",
        date(2012, 12, 28),
        date(2013, 7, 1),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国公司法_20131228",
        "company-law",
        "中华人民共和国公司法",
        "company-law@2013-12-28",
        date(2013, 12, 28),
        date(2014, 3, 1),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国公司法_20181026",
        "company-law",
        "中华人民共和国公司法",
        "company-law@2018-10-26",
        date(2018, 10, 26),
        date(2018, 10, 26),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国公司法_20231229",
        "company-law",
        "中华人民共和国公司法",
        "company-law@2023-12-29",
        date(2023, 12, 29),
        date(2024, 7, 1),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国专利法_20081227",
        "patent-law",
        "中华人民共和国专利法",
        "patent-law@2008-12-27",
        date(2008, 12, 27),
        date(2009, 10, 1),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国专利法_20201017",
        "patent-law",
        "中华人民共和国专利法",
        "patent-law@2020-10-17",
        date(2020, 10, 17),
        date(2021, 6, 1),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国商标法_20190423",
        "trademark-law",
        "中华人民共和国商标法",
        "trademark-law@2019-04-23",
        date(2019, 4, 23),
        date(2019, 11, 1),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国商标法_20260626",
        "trademark-law",
        "中华人民共和国商标法",
        "trademark-law@2026-06-26",
        date(2026, 6, 26),
        date(2027, 1, 1),
        SOURCE_STATUS_PUBLISHED_NOT_EFFECTIVE,
    ),
    Stage4SourceSpec(
        "中华人民共和国著作权法_20100226",
        "copyright-law",
        "中华人民共和国著作权法",
        "copyright-law@2010-02-26",
        date(2010, 2, 26),
        date(2010, 4, 1),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国著作权法_20201111",
        "copyright-law",
        "中华人民共和国著作权法",
        "copyright-law@2020-11-11",
        date(2020, 11, 11),
        date(2021, 6, 1),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国刑法_20090827",
        "criminal-law",
        "中华人民共和国刑法",
        "criminal-law@2009-08-27",
        date(2009, 8, 27),
        date(2009, 8, 27),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国刑法_20201226",
        "criminal-law",
        "中华人民共和国刑法",
        "criminal-law@2020-12-26",
        date(2020, 12, 26),
        date(2021, 3, 1),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国刑法修正案（十）_20171104",
        "criminal-law",
        "中华人民共和国刑法修正案（十）",
        "criminal-amendment-10@2017-11-04",
        date(2017, 11, 4),
        date(2017, 11, 4),
        SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
        "AMENDMENT",
    ),
    Stage4SourceSpec(
        "中华人民共和国刑法修正案（十一）_20201226",
        "criminal-law",
        "中华人民共和国刑法修正案（十一）",
        "criminal-amendment-11@2020-12-26",
        date(2020, 12, 26),
        date(2021, 3, 1),
        SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
        "AMENDMENT",
    ),
    Stage4SourceSpec(
        "中华人民共和国刑法修正案（十二）_20231229",
        "criminal-law",
        "中华人民共和国刑法修正案（十二）",
        "criminal-amendment-12@2023-12-29",
        date(2023, 12, 29),
        date(2024, 3, 1),
        SOURCE_STATUS_SUPPLEMENTAL_AMENDMENT,
        "AMENDMENT",
    ),
    Stage4SourceSpec(
        "中华人民共和国宪法（1982年）_19821204",
        "constitution",
        "中华人民共和国宪法",
        "constitution@1982-12-04",
        date(1982, 12, 4),
        date(1982, 12, 4),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国宪法（2018年修正文本）_20180311",
        "constitution",
        "中华人民共和国宪法",
        "constitution@2018-03-11",
        date(2018, 3, 11),
        date(2018, 3, 11),
        SOURCE_STATUS_CURRENT,
    ),
    Stage4SourceSpec(
        "中华人民共和国治安管理处罚法_20121026",
        "public-security-administration-punishment-law",
        "中华人民共和国治安管理处罚法",
        "public-security-administration-punishment-law@2012-10-26",
        date(2012, 10, 26),
        date(2012, 10, 26),
        SOURCE_STATUS_HISTORICAL,
    ),
    Stage4SourceSpec(
        "中华人民共和国治安管理处罚法_20250627",
        "public-security-administration-punishment-law",
        "中华人民共和国治安管理处罚法",
        "public-security-administration-punishment-law@2025-06-27",
        date(2025, 6, 27),
        date(2026, 1, 1),
        SOURCE_STATUS_CURRENT,
    ),
)

_BY_FILENAME = {spec.filename_stem: spec for spec in _SPECS}


def inspect_stage4_source(source_path: str | Path) -> Stage4SourceCandidate:
    """Read one registered local DOCX into a non-authoritative candidate record."""
    path = Path(source_path)
    if path.suffix.lower() != ".docx":
        raise StatuteSourceIntakeError("阶段 4 法规候选仅接受 DOCX 原件")
    spec = _BY_FILENAME.get(path.stem)
    if spec is None:
        raise StatuteSourceIntakeError(f"未登记的阶段 4 法规文件: {path.name}")
    if not path.is_file():
        raise StatuteSourceIntakeError(f"法规原件不存在: {path}")

    content = "\n".join(segment["text"] for segment in parse_document(path)).strip()
    if spec.law_name not in content:
        raise StatuteSourceIntakeError(f"正文标题与文件名不一致，未找到: {spec.law_name}")
    if not content:
        raise StatuteSourceIntakeError("法规原件未提取到正文")

    raw_bytes = path.read_bytes()
    return Stage4SourceCandidate(
        source_path=path.resolve(),
        law_slug=spec.law_slug,
        law_name=spec.law_name,
        version_id=spec.version_id,
        promulgated_on=spec.promulgated_on,
        effective_from=spec.effective_from,
        source_status=spec.source_status,
        raw_sha256=sha256(raw_bytes).hexdigest(),
        content_sha256=sha256(content.encode("utf-8")).hexdigest(),
        content=content,
        document_type=spec.document_type,
    )


def scan_stage4_source_directory(source_dir: str | Path) -> Stage4SourceScan:
    """Inspect only filename-registered DOCX files from a supplied local directory."""
    directory = Path(source_dir)
    if not directory.is_dir():
        raise StatuteSourceIntakeError(f"法规来源目录不存在: {directory}")

    candidates: list[Stage4SourceCandidate] = []
    skipped_files: list[Path] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".docx" or path.stem not in _BY_FILENAME:
            skipped_files.append(path)
            continue
        candidates.append(inspect_stage4_source(path))
    return Stage4SourceScan(tuple(candidates), tuple(skipped_files))
