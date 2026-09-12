"""
测试法条引用自校验
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reasoning.self_verify import SelfVerifier, Citation, VerificationStatus


class MockLLM:
    """模拟LLM"""

    def invoke(self, prompt):
        response = MagicMock()

        if "验证" in prompt:
            response.content = '''{
                "is_consistent": true,
                "consistency_score": 0.95,
                "issues": [],
                "suggestions": [],
                "verification_details": [
                    {
                        "cited_text": "依据本法第143条",
                        "original_text": "具备下列条件的民事法律行为有效：...",
                        "is_match": true
                    }
                ]
            }'''
        elif "修正" in prompt:
            response.content = "修正后的回答内容"

        return response


class TestSelfVerifier:
    """测试自校验器"""

    @pytest.fixture
    def verifier(self):
        """创建校验器实例（v1.7+ 使用 create_llm 工厂，patch 工厂而非过时的 ChatOpenAI）"""
        with patch('src.reasoning.self_verify.create_llm', return_value=MockLLM()):
            return SelfVerifier()
    
    def test_extract_citations_brackets(self, verifier):
        """测试提取【法条编号】格式的引用"""
        answer = "根据【民法典第143条】的规定，具备下列条件的民事法律行为有效。"
        citations = verifier.extract_citations(answer)
        
        assert len(citations) >= 1
        assert any("143" in c.article_id for c in citations)
    
    def test_extract_citations_by_clause(self, verifier):
        """测试提取'依据...条'格式的引用"""
        answer = "依据本法第一百四十二条的规定确定争议条款的含义。"
        citations = verifier.extract_citations(answer)
        
        assert len(citations) >= 1
    
    def test_verify_citation(self, verifier):
        """测试校验单个引用"""
        citation = Citation(
            article_id="第143条",
            citation_text="依据本法第143条",
            position=(0, 10)
        )
        
        def mock_retriever(article_id):
            result = MagicMock()
            result.full_content = "具备下列条件的民事法律行为有效：（一）行为人具有相应的民事行为能力；（二）意思表示真实；（三）不违反法律、行政法规的强制性规定，不违背公序良俗。"
            return result
        
        is_consistent, original_text = verifier.verify_citation(citation, mock_retriever)
        
        assert is_consistent
        assert original_text is not None
    
    def test_verify_with_multiple_citations(self, verifier):
        """测试多引用校验"""
        answer = """
根据【民法典第143条】的规定，具备下列条件的民事法律行为有效。
同时，依据本法第465条，依法成立的合同受法律保护。
"""
        
        def mock_retriever(article_id):
            result = MagicMock()
            result.full_content = "法条内容"
            return result
        
        result = verifier.verify(answer, mock_retriever)
        
        assert result is not None
        assert result.status in [VerificationStatus.PASS, VerificationStatus.FAIL, VerificationStatus.PARTIAL]
    
    def test_verify_no_citations(self, verifier):
        """测试无引用的回答"""
        answer = "合同是民事主体之间设立、变更、终止民事法律关系的协议。"
        
        def mock_retriever(article_id):
            return None
        
        result = verifier.verify(answer, mock_retriever)
        
        assert result.status == VerificationStatus.CANNOT_VERIFY
    
    def test_correct_answer(self, verifier):
        """测试修正功能"""
        from src.reasoning.self_verify import VerificationResult
        
        verification_result = VerificationResult(
            status=VerificationStatus.PARTIAL,
            citations=[],
            overall_consistency=0.5,
            issues=["部分引用不准确"],
            suggestions=["请核实法条内容"]
        )
        
        original_answer = "根据民法典第143条的规定，合同有效。"
        corrected = verifier.correct(original_answer, verification_result)
        
        assert corrected is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
