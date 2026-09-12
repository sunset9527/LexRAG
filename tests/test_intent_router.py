"""
测试查询意图路由
"""

import pytest
import sys
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrieval.intent_router import IntentRouter, IntentType, QueryIntent


class MockLLM:
    """模拟LLM"""
    
    def invoke(self, prompt):
        response = MagicMock()

        if "意图类型" in prompt:
            query_match = re.search(r"用户问题：(.*?)\n\n", prompt, re.DOTALL)
            query = query_match.group(1) if query_match else ""
            if "类似的案例" in query:
                intent_type = "case_query"
            elif "租房纠纷" in query:
                intent_type = "legal_application"
            elif "定金和订金" in query:
                intent_type = "comparison"
            else:
                intent_type = "law_article"
            response.content = f'''{{
                "intent_type": "{intent_type}",
                "confidence": 0.95,
                "key_entities": ["民法典第143条"],
                "sub_questions": [],
                "search_keywords": ["民法典", "143条"],
                "reasoning_chain": ["用户直接询问法条内容"]
            }}'''
        elif "拆解" in prompt:
            response.content = '''{
                "sub_questions": ["合同成立的条件是什么？"],
                "reasoning": "单一问题无需拆解"
            }'''
        
        return response


class TestIntentRouter:
    """测试意图路由器"""
    
    @pytest.fixture
    def router(self):
        """创建路由器实例"""
        with patch('src.retrieval.intent_router.create_llm') as mock:
            mock.return_value = MockLLM()
            return IntentRouter()
    
    def test_classify_law_article_intent(self, router):
        """测试法条查询意图识别"""
        query = "民法典第143条规定了什么？"
        intent = router.classify_intent(query)
        
        assert intent.intent_type == IntentType.LAW_ARTICLE
        assert intent.confidence > 0.8
    
    def test_classify_case_query_intent(self, router):
        """测试案例查询意图识别"""
        query = "有没有类似的案例？"
        intent = router.classify_intent(query)
        
        assert intent.intent_type == IntentType.CASE_QUERY
    
    def test_classify_legal_application_intent(self, router):
        """测试法律适用意图识别"""
        query = "租房纠纷怎么处理？"
        intent = router.classify_intent(query)
        
        assert intent.intent_type == IntentType.LEGAL_APPLICATION
    
    def test_classify_comparison_intent(self, router):
        """测试对比分析意图识别"""
        query = "定金和订金有什么区别？"
        intent = router.classify_intent(query)
        
        assert intent.intent_type == IntentType.COMPARISON
    
    def test_route_query(self, router):
        """测试路由功能"""
        query = "合同成立需要哪些条件？"
        intent = router.route_query(query)
        
        assert intent is not None
        assert intent.intent_type is not None
    
    def test_get_retriever_type(self, router):
        """测试检索器类型选择"""
        law_intent = QueryIntent(
            intent_type=IntentType.LAW_ARTICLE,
            confidence=0.9
        )
        retriever_type = router.get_retriever_type(law_intent)
        assert retriever_type == "law_retriever"
        
        case_intent = QueryIntent(
            intent_type=IntentType.CASE_QUERY,
            confidence=0.9
        )
        retriever_type = router.get_retriever_type(case_intent)
        assert retriever_type == "case_retriever"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
