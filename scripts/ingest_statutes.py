"""准备、校验并入库 v1.9 模块 1 的核心法规文本。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.statute_ingestion import (  # noqa: E402
    StatuteDefinition,
    StatuteIngestionRunner,
    prepare_statute_sources,
    validate_clean_law_text,
)

SOURCE_DIRECTORY = Path(r"E:\个人发展\002职业\项目1：RAG法律")
RAW_DIRECTORY = PROJECT_ROOT / "data" / "laws" / "raw"
CLEAN_TEXT_DIRECTORY = PROJECT_ROOT / "data" / "laws"

STATUTE_DEFINITIONS = (
    StatuteDefinition(
        "criminal-law",
        "中华人民共和国刑法",
        "criminal",
        "criminal-code",
        terminal_article_number=452,
        first_article_marker="为了惩罚犯罪",
    ),
    StatuteDefinition(
        "labor-law",
        "中华人民共和国劳动法",
        "labor",
        "labor-code",
        terminal_article_number=107,
        first_article_marker="为了保护劳动者的合法权益",
    ),
    StatuteDefinition(
        "labor-contract-law",
        "中华人民共和国劳动合同法",
        "labor",
        "labor-code",
        terminal_article_number=98,
        first_article_marker="为了完善劳动合同制度",
    ),
    StatuteDefinition(
        "company-law",
        "中华人民共和国公司法",
        "company",
        "company-code",
        terminal_article_number=218,
        first_article_marker="为了规范公司的组织和行为",
    ),
    StatuteDefinition(
        "patent-law",
        "中华人民共和国专利法",
        "intellectual-property",
        "intellectual-property-code",
        terminal_article_number=69,
        first_article_marker="为了保护专利权人的合法权益",
    ),
    StatuteDefinition(
        "trademark-law",
        "中华人民共和国商标法",
        "intellectual-property",
        "intellectual-property-code",
        terminal_article_number=73,
        first_article_marker="为了加强商标管理",
    ),
    StatuteDefinition(
        "copyright-law",
        "中华人民共和国著作权法",
        "intellectual-property",
        "intellectual-property-code",
        terminal_article_number=61,
        first_article_marker="为保护文学、艺术和科学作品作者的著作权",
    ),
)


def source_files() -> dict[str, Path]:
    """解析用户资料目录中四份已确认的 EPUB 来源。"""
    patterns = {
        "criminal-code": "*刑事法律法规全书*.epub",
        "labor-code": "*劳动法*.epub",
        "company-code": "*公司法典*.epub",
        "intellectual-property-code": "*知识产权法典*.epub",
    }
    resolved: dict[str, Path] = {}
    for source_id, pattern in patterns.items():
        matches = list(SOURCE_DIRECTORY.glob(pattern))
        if len(matches) != 1:
            raise FileNotFoundError(f"来源文件应唯一匹配 {pattern}，实际匹配 {len(matches)} 个")
        resolved[source_id] = matches[0]
    return resolved


def selected_definitions(slug: str | None) -> tuple[StatuteDefinition, ...]:
    """按 slug 选择一个法规，省略时选择全部法规。"""
    if slug is None:
        return STATUTE_DEFINITIONS
    selected = tuple(item for item in STATUTE_DEFINITIONS if item.slug == slug)
    if not selected:
        raise ValueError(f"未知法律 slug: {slug}")
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--prepare", action="store_true", help="从原始 EPUB 重建 raw、clean 与 manifest"
    )
    action.add_argument("--validate-only", action="store_true", help="只校验已生成的 clean 文本")
    action.add_argument("--all", action="store_true", help="将全部已校验法规写入独立知识库")
    parser.add_argument("--law", help="单独处理的法规 slug")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    definitions = selected_definitions(args.law)
    if args.prepare:
        manifest = prepare_statute_sources(
            source_files(),
            definitions,
            raw_directory=RAW_DIRECTORY,
            clean_text_directory=CLEAN_TEXT_DIRECTORY,
            extracted_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        print(f"资料准备完成：{len(manifest['laws'])} 部法律，来源 {len(manifest['sources'])} 份")
        return 0

    if args.validate_only:
        for definition in definitions:
            content = (CLEAN_TEXT_DIRECTORY / f"{definition.slug}.txt").read_text(encoding="utf-8")
            report = validate_clean_law_text(content, definition)
            print(
                f"{definition.slug}: {report.article_count} 条，"
                f"第 {report.first_article_number} 条至第 {report.last_article_number} 条，"
                f"sha256={report.clean_text_sha256}"
            )
        return 0

    from app.db import session as db_session
    from app.db.session import init_db
    from app.services.knowledge_base_service import KnowledgeBaseService

    init_db()
    summary = StatuteIngestionRunner(KnowledgeBaseService(db_session.SessionLocal)).ingest_all(
        definitions,
        clean_text_directory=CLEAN_TEXT_DIRECTORY,
    )
    for item in summary.succeeded:
        print(f"完成：{item.slug}，chunk {item.knowledge_base['chunk_count']} 个")
    for item in summary.failed:
        print(f"失败：{item.slug}，原因：{item.reason}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
