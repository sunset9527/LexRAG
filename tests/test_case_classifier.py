"""年度案例的规则案由分类测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.case_classifier import RuleBasedCaseCauseClassifier


def test_classifier_uses_evidence_and_marks_unknown_for_manual_review():
    classifier = RuleBasedCaseCauseClassifier(domain="labor")

    known = classifier.classify("用人单位未签订劳动合同，双方就是否存在劳动关系发生争议")
    unknown = classifier.classify("当事人之间发生争议，法院依法审理")

    assert known == "确认劳动关系纠纷"
    assert unknown == "未分类（待人工校验）"
