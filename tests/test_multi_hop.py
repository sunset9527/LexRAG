"""
测试多跳法律推理
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reasoning.multi_hop import MultiHopReasoner, SubQuestion


class MockLLM:
    """模拟LLM"""
    
    def invoke(self, prompt):
        response = MagicMock()
        
        if '"sub_questions"' in prompt:
            response.content = '''{
                "sub_questions": [
                    {"id": "q1", "question": "什么是合同？", "reasoning_needed": ["合同定义"]},
                    {"id": "q2", "question": "合同成立需要什么条件？", "reasoning_needed": ["合同成立"]}
                ],
                "reasoning_chain": ["问题拆解完成"]
            }'''
        elif "子问题" in prompt:
            response.content = "根据检索到的法条，合同是民事主体之间设立、变更、终止民事法律关系的协议。"
        elif "综合" in prompt:
            response.content = "综合以上分析，合同是设立、变更、终止民事法律关系的协议，其成立需要满足法定条件。"
        
        return response


class TestMultiHopReasoner:
    """测试多跳推理器"""
    
    @pytest.fixture
    def reasoner(self):
        """创建推理器实例"""
        with patch('src.reasoning.multi_hop.create_llm') as mock:
            mock.return_value = MockLLM()
            return MultiHopReasoner()
    
    def test_decompose_simple_query(self, reasoner):
        """测试简单问题分解"""
        query = "合同成立需要哪些条件？"
        sub_questions = reasoner.decompose(query)
        
        assert len(sub_questions) > 0
        assert all(isinstance(sq, SubQuestion) for sq in sub_questions)
    
    def test_decompose_complex_query(self, reasoner):
        """测试复杂问题分解"""
        query = "签订房屋买卖合同需要注意哪些法律问题？"
        sub_questions = reasoner.decompose(query)
        
        assert len(sub_questions) >= 2
    
    def test_answer_sub_question(self, reasoner):
        """测试子问题回答"""
        sq = SubQuestion("q1", "什么是合同？", [])
        retrieved_content = "合同是民事主体之间设立、变更、终止民事法律关系的协议。"
        
        answer = reasoner.answer_sub_question(sq, retrieved_content)
        
        assert answer is not None
        assert len(answer) > 0
    
    def test_synthesize(self, reasoner):
        """测试综合回答"""
        sub_questions = [
            SubQuestion("q1", "什么是合同？", []),
            SubQuestion("q2", "合同成立的条件？", [])
        ]
        sub_questions[0].answer = "合同是协议"
        sub_questions[1].answer = "需要满足法定条件"
        
        final_answer = reasoner.synthesize(
            "合同的相关问题",
            sub_questions
        )
        
        assert final_answer is not None
        assert len(final_answer) > 0
    
    def test_reason_workflow(self, reasoner):
        """测试完整推理流程"""
        def mock_retrieval(query):
            return "检索到的相关法条内容"
        
        result = reasoner.reason(
            "合同成立需要哪些条件？",
            mock_retrieval
        )
        
        assert "final_answer" in result
        assert "sub_questions" in result
        assert "reasoning_steps" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
