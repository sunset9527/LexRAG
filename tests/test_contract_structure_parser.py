"""合同结构化解析的可追溯性测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.legal_document_structure import structure_document


def test_contract_parser_extracts_numbered_clauses_with_source_evidence():
    """合同字段只能来自对应条款，并绑定页码和原文依据。"""
    result = structure_document(
        [
            (
                1,
                """劳动合同
第一条 当事人
甲方：甲公司
乙方：张三
第二条 工作内容
乙方担任研发工程师。
第三条 劳动报酬
甲方每月支付工资10000元。""",
            ),
            (
                2,
                """第四条 违约责任
违约方应支付违约金。
第五条 争议解决
因履行本合同发生争议，向北京市朝阳区人民法院提起诉讼。""",
            ),
        ]
    )

    assert result.document_type == "contract"
    assert result.content["parties"]["value"] == "甲方：甲公司\n乙方：张三"
    assert result.content["parties"]["page_number"] == 1
    assert result.content["subject"]["value"] == "乙方担任研发工程师。"
    assert result.content["remuneration"]["value"] == "甲方每月支付工资10000元。"
    assert result.content["breach"]["page_number"] == 2
    assert result.content["dispute_resolution"]["value"].startswith("因履行本合同发生争议")
    assert result.content["jurisdiction"]["value"] == "北京市朝阳区人民法院"
    assert result.content["exemption"] is None
    for field in (
        "parties",
        "subject",
        "remuneration",
        "breach",
        "dispute_resolution",
        "jurisdiction",
    ):
        assert result.content[field]["extraction_method"] == "rule"
        assert result.content[field]["evidence_text"] in "\n".join(text for _, text in result.pages)


def test_contract_parser_accepts_decimal_clause_numbers():
    """部分合同用 1.1 形式编号，仍需保留对应条款范围和页码。"""
    result = structure_document(
        [
            (
                3,
                """服务合同
甲方：甲公司
乙方：乙公司
1.1 服务内容
乙方提供系统维护服务。
1.2 服务期限
本合同期限为一年。""",
            )
        ]
    )

    assert result.document_type == "contract"
    assert [item["number"] for item in result.content["clauses"]] == ["1.1", "1.2"]
    assert result.content["subject"]["value"] == "乙方提供系统维护服务。"
    assert result.content["term"]["page_number"] == 3
