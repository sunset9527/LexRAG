"""案例来源登记与可追溯性测试。"""

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import app.models.case_source  # noqa: F401
from app.db.base import Base
from app.services.case_ingestion_service import CaseIngestionService
from src.ingestion.case_parser import AnnualCaseParser


def test_register_source_records_hash_pages_and_user_provided_origin(tmp_path):
    """案例 PDF 必须带哈希、页数和真实来源标记，不能伪装为指导案例。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    source_file = tmp_path / "劳动纠纷年度案例.pdf"
    source_file.write_bytes(b"case-book")
    service = CaseIngestionService(
        sessionmaker(bind=engine, expire_on_commit=False),
        page_counter=lambda path: 387 if path == source_file else 0,
    )

    source = service.register_source(
        path=source_file,
        title="中国法院2025年度案例·劳动纠纷（含社会保险纠纷）",
        domain="labor",
        publisher_note="国家法官学院、最高人民法院司法案例研究院编；用户提供文件",
    )

    assert source["status"] == "PENDING"
    assert source["page_count"] == 387
    assert source["origin_label"] == "用户提供的年度案例汇编"
    assert len(source["file_sha256"]) == 64


def test_persist_case_keeps_structured_fields_and_source_pages(tmp_path):
    """结构化案例落库后必须保留原始来源页码和提取警告。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    source_file = tmp_path / "劳动纠纷年度案例.pdf"
    source_file.write_bytes(b"case-book")
    service = CaseIngestionService(
        sessionmaker(bind=engine, expire_on_commit=False), page_counter=lambda _path: 1
    )
    source = service.register_source(
        path=source_file, title="劳动纠纷", domain="labor", publisher_note="用户提供"
    )
    parsed = AnnualCaseParser(domain="labor").parse_case(
        sequence_no=1,
        case_cause="确认劳动关系纠纷",
        pages=[
            {
                "page": 14,
                "text": "某甲诉某公司劳动争议案\n【案件焦点】是否存在劳动关系。\n【法院裁判要旨】审查从属性。\n判决如下：驳回诉讼请求。",
            }
        ],
    )

    case = service.persist_case(source_id=source["id"], sequence_no=1, parsed=parsed)

    assert case["domain"] == "labor"
    assert case["case_cause"] == "确认劳动关系纠纷"
    assert case["source_start_page"] == 14
    assert "未识别法官后语" not in case["extraction_warnings"]


def test_list_cases_filters_by_domain_and_case_cause(tmp_path):
    """案例列表应允许按领域和案由过滤，不读取其他领域的案例。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    file = tmp_path / "cases.pdf"
    file.write_bytes(b"cases")
    service = CaseIngestionService(
        sessionmaker(bind=engine, expire_on_commit=False), page_counter=lambda _path: 1
    )
    source = service.register_source(
        path=file, title="案例", domain="labor", publisher_note="用户提供"
    )
    parser = AnnualCaseParser(domain="labor")
    service.persist_case(
        source_id=source["id"],
        sequence_no=1,
        parsed=parser.parse_case(
            sequence_no=1,
            case_cause="确认劳动关系纠纷",
            pages=[
                {
                    "page": 1,
                    "text": "某甲诉某公司案\n【案件焦点】劳动关系。\n【法院裁判要旨】审查从属性。\n判决如下：驳回。",
                }
            ],
        ),
    )
    service.persist_case(
        source_id=source["id"],
        sequence_no=2,
        parsed=parser.parse_case(
            sequence_no=2,
            case_cause="劳动报酬纠纷",
            pages=[
                {
                    "page": 2,
                    "text": "某乙诉某公司案\n【案件焦点】工资。\n【法院裁判要旨】审查欠薪。\n判决如下：支持。",
                }
            ],
        ),
    )

    cases = service.list_cases(domain="labor", case_cause="确认劳动关系纠纷")

    assert len(cases) == 1
    assert cases[0]["case_cause"] == "确认劳动关系纠纷"


def test_list_sources_and_get_case_keep_the_traceability_fields(tmp_path):
    """页面可分别读取案例源处理状态和单案的完整可追溯信息。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    file = tmp_path / "cases.pdf"
    file.write_bytes(b"cases")
    service = CaseIngestionService(
        sessionmaker(bind=engine, expire_on_commit=False), page_counter=lambda _path: 2
    )
    source = service.register_source(
        path=file, title="劳动案例", domain="labor", publisher_note="用户提供"
    )
    parsed = AnnualCaseParser(domain="labor").parse_case(
        sequence_no=1,
        case_cause="确认劳动关系纠纷",
        pages=[
            {
                "page": 2,
                "text": "某甲诉某公司案\n【案件焦点】劳动关系。\n【法院裁判要旨】审查从属性。\n判决如下：驳回。",
            }
        ],
    )
    created = service.persist_case(source_id=source["id"], sequence_no=1, parsed=parsed)

    sources = service.list_sources(domain="labor")
    case = service.get_case(created["id"])

    assert sources == [source]
    assert case["source_id"] == source["id"]
    assert case["source_start_page"] == 2
