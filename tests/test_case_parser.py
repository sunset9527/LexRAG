"""年度案例 OCR 文本的结构化解析测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.case_parser import AnnualCaseParser


def test_parser_extracts_labeled_case_sections_and_source_pages():
    """有稳定标题的 OCR 案例应拆出结构字段，并保留起止页码。"""
    pages = [
        {
            "page": 14,
            "text": "确认劳动关系\n某甲诉某餐饮公司劳动争议案\n"
            "【案件焦点】双方是否存在劳动关系。\n"
            "【法院裁判要旨】应审查经济从属性和管理从属性。\n"
            "依据《中华人民共和国劳动法》第七十八条，判决如下：驳回某甲全部诉讼请求。",
        },
        {
            "page": 15,
            "text": "【法官后语】餐饮后厨用工可能构成劳务外包。",
        },
    ]

    case = AnnualCaseParser(domain="labor").parse_case(
        sequence_no=1,
        case_cause="确认劳动关系纠纷",
        pages=pages,
    )

    assert case.title == "某甲诉某餐饮公司劳动争议案"
    assert case.case_cause == "确认劳动关系纠纷"
    assert case.issues == "双方是否存在劳动关系。"
    assert case.court_reasoning.startswith("应审查经济从属性和管理从属性。")
    assert "驳回某甲全部诉讼请求" in case.judgment_result
    assert case.judge_commentary == "餐饮后厨用工可能构成劳务外包。"
    assert case.legal_basis == ["《中华人民共和国劳动法》第七十八条"]
    assert (case.source_start_page, case.source_end_page) == (14, 15)
    assert case.extraction_warnings == []
