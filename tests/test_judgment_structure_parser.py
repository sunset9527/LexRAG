"""判决书结构化解析的可追溯性测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.legal_document_structure import structure_document


def test_judgment_parser_extracts_sections_and_legal_basis_with_evidence():
    """判决书字段和引用法条都必须回指当前输入文本与页码。"""
    result = structure_document(
        [
            (
                3,
                """北京市朝阳区人民法院民事判决书
原告：张三。
被告：甲公司。
案由：劳动争议。
原告诉称：甲公司拖欠劳动报酬。
本院查明：张三于2024年1月入职。
本院认为：甲公司应依法支付劳动报酬。
依照《中华人民共和国劳动合同法》第三条之规定，判决如下：甲公司于十日内支付张三工资10000元。""",
            )
        ]
    )

    assert result.document_type == "judgment"
    assert result.content["parties"]["value"] == "原告：张三。\n被告：甲公司。"
    assert result.content["case_cause"]["value"] == "劳动争议"
    assert result.content["claims"]["value"] == "甲公司拖欠劳动报酬。"
    assert result.content["facts"]["value"] == "张三于2024年1月入职。"
    assert result.content["court_reasoning"]["value"] == "甲公司应依法支付劳动报酬。"
    assert result.content["judgment_result"]["value"].startswith("甲公司于十日内支付")
    assert result.content["legal_basis"][0]["value"] == "《中华人民共和国劳动合同法》第三条"
    for field in ("parties", "case_cause", "claims", "facts", "court_reasoning", "judgment_result"):
        assert result.content[field]["page_number"] == 3
        assert result.content[field]["evidence_text"]
        assert result.content[field]["extraction_method"] == "rule"
