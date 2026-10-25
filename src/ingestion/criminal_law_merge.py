"""Deterministic, reviewable construction of the Criminal Law Amendment XII candidate.

This module deliberately accepts only explicit full-article replacement patches.  It
does not infer amendments from natural language and cannot make a generated text
indexable; source review remains a separate service action.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from src.ingestion.statute_source_intake import (
    SOURCE_STATUS_CURRENT,
    Stage4SourceCandidate,
)


class CriminalLawMergeError(ValueError):
    """The supplied patch manifest cannot safely produce a consolidated text."""


@dataclass(frozen=True)
class CriminalLawPatch:
    article_number: str
    amendment_item_number: int
    replacement_text: str


@dataclass(frozen=True)
class MergedCriminalLawText:
    content: str
    content_sha256: str
    base_content_sha256: str
    amendment_content_sha256: str


_ARTICLE_START = re.compile(r"^第([〇零一二三四五六七八九十百千\d]+)条(?!之)")
_ANY_ARTICLE_START = re.compile(r"^第[〇零一二三四五六七八九十百千\d]+条")
_CHINESE_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000}
_AMENDMENT_12_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "laws"
    / "stage4"
    / "criminal-law-amendment-12-patches.json"
)


def merge_criminal_law_amendment_12(
    base_content: str,
    amendment_content: str,
    patches: Iterable[CriminalLawPatch],
) -> MergedCriminalLawText:
    """Replace only manifest-declared Criminal Law articles with complete text."""
    normalized_patches = tuple(patches)
    targets = _validate_patches(normalized_patches)
    lines = [line.strip() for line in base_content.splitlines() if line.strip()]
    article_starts = _find_article_starts(lines)

    for target in targets:
        if target not in article_starts:
            raise CriminalLawMergeError(f"待替换的第{target}条不存在")
        if len(article_starts[target]) != 1:
            raise CriminalLawMergeError(f"待替换的第{target}条不唯一")

    replacement_by_target = {patch.article_number: patch for patch in normalized_patches}
    merged_lines: list[str] = []
    index = 0
    while index < len(lines):
        article_number = _article_number(lines[index])
        if article_number not in replacement_by_target:
            merged_lines.append(lines[index])
            index += 1
            continue

        patch = replacement_by_target[article_number]
        merged_lines.extend(line.strip() for line in patch.replacement_text.splitlines() if line.strip())
        index += 1
        while index < len(lines) and not _ANY_ARTICLE_START.match(lines[index]):
            index += 1

    content = "\n".join(merged_lines)
    return MergedCriminalLawText(
        content=content,
        content_sha256=_hash(content),
        base_content_sha256=_hash(base_content),
        amendment_content_sha256=_hash(amendment_content),
    )


def build_consolidated_candidate(
    base: Stage4SourceCandidate,
    amendment: Stage4SourceCandidate,
    patches: Iterable[CriminalLawPatch],
) -> Stage4SourceCandidate:
    """Create an unverified current-version candidate from reviewed source inputs.

    The returned source deliberately stays ``PENDING_REVIEW``.  A separate
    reviewer must inspect it and call the existing verification flow before it
    can be selected as a version chain's consolidated text.
    """
    if base.law_slug != "criminal-law" or amendment.law_slug != "criminal-law":
        raise CriminalLawMergeError("刑法合并只能使用刑法基准全文和修正案")
    if amendment.document_type != "AMENDMENT":
        raise CriminalLawMergeError("刑法合并输入必须包含修正案原件")

    merged = merge_criminal_law_amendment_12(base.content, amendment.content, patches)
    generated_raw_hash = _hash(
        f"{base.raw_sha256}:{amendment.raw_sha256}:{merged.content_sha256}"
    )
    return Stage4SourceCandidate(
        source_path=Path("generated") / "criminal-law@2024-03-01.txt",
        law_slug="criminal-law",
        law_name="中华人民共和国刑法",
        version_id="criminal-law@2024-03-01",
        promulgated_on=date(2023, 12, 29),
        effective_from=date(2024, 3, 1),
        source_status=SOURCE_STATUS_CURRENT,
        raw_sha256=generated_raw_hash,
        content_sha256=merged.content_sha256,
        content=merged.content,
        document_type="STATUTE",
        parser_version="criminal-amendment-12-merge-v1",
    )


def load_amendment_12_patch_manifest() -> tuple[CriminalLawPatch, ...]:
    """Load the reviewable, source-transcribed Amendment XII replacement map."""
    payload = json.loads(_AMENDMENT_12_MANIFEST.read_text(encoding="utf-8"))
    if payload.get("amendment_version_id") != "criminal-amendment-12@2023-12-29":
        raise CriminalLawMergeError("修正案十二补丁清单版本不匹配")
    raw_patches = payload.get("patches")
    if not isinstance(raw_patches, list):
        raise CriminalLawMergeError("修正案十二补丁清单格式错误")
    return tuple(
        CriminalLawPatch(
            article_number=str(item["article_number"]),
            amendment_item_number=int(item["amendment_item_number"]),
            replacement_text=str(item["replacement_text"]),
        )
        for item in raw_patches
    )


def _validate_patches(patches: tuple[CriminalLawPatch, ...]) -> set[str]:
    if not patches:
        raise CriminalLawMergeError("修正案补丁清单不能为空")
    targets: set[str] = set()
    for patch in patches:
        if not patch.article_number.isdigit() or int(patch.article_number) <= 0:
            raise CriminalLawMergeError("补丁条号必须是正整数")
        if patch.article_number in targets:
            raise CriminalLawMergeError(f"第{patch.article_number}条存在重复补丁")
        if patch.amendment_item_number <= 0:
            raise CriminalLawMergeError("修正案条目序号必须为正整数")
        if _article_number(patch.replacement_text.strip()) != patch.article_number:
            raise CriminalLawMergeError("补丁必须提供目标条号的完整替换条文")
        targets.add(patch.article_number)
    return targets


def _find_article_starts(lines: list[str]) -> dict[str, list[int]]:
    positions: dict[str, list[int]] = {}
    for index, line in enumerate(lines):
        article_number = _article_number(line)
        if article_number is not None:
            positions.setdefault(article_number, []).append(index)
    return positions


def _article_number(line: str) -> str | None:
    match = _ARTICLE_START.match(line)
    if match is None:
        return None
    raw = match.group(1)
    if raw.isdigit():
        return str(int(raw))
    total = 0
    pending = 0
    for character in raw:
        if character in _CHINESE_DIGITS:
            pending = _CHINESE_DIGITS[character]
        elif character in _CHINESE_UNITS:
            total += (pending or 1) * _CHINESE_UNITS[character]
            pending = 0
        else:
            return None
    return str(total + pending)


def _hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()
