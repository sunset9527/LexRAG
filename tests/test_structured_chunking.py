"""
测试法律文档结构化切分
"""

import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.law_parser import LawParser, LawArticle
from src.ingestion.chunker import StructuredLawChunker


class TestLawParser:
    """测试法律文档解析器"""
    
    def test_parse_simple_article(self):
        """测试解析简单法条"""
        parser = LawParser()
        content = """
第四百六十三条 本编调整因合同产生的民事法律关系。

第四百六十四条 合同是民事主体之间设立、变更、终止民事法律关系的协议。

婚姻、收养、监护等有关身份关系的协议，适用有关该身份关系的法律规定。
"""
        articles = parser.parse_law_content(content, "民法典")
        
        assert len(articles) == 2
        assert articles[0].article_number == "463"
        assert "合同" in articles[0].content
        assert articles[1].article_number == "464"
    
    def test_extract_references(self):
        """测试提取法条引用"""
        parser = LawParser()
        content = "当事人对合同条款的理解有争议的，应当依据本法第一百四十二条第一款的规定确定争议条款的含义。"
        articles = parser.parse_law_content(content, "民法典")
        
        assert len(articles) == 1
        assert "第142条" in articles[0].references


class TestStructuredChunker:
    """测试结构化切分器"""
    
    def test_chunk_articles(self):
        """测试法条切分"""
        parser = LawParser()
        content = """
第四百六十三条 本编调整因合同产生的民事法律关系。

第四百六十四条 合同是民事主体之间设立、变更、终止民事法律关系的协议。
"""
        articles = parser.parse_law_content(content, "民法典")
        
        chunker = StructuredLawChunker(version="test")
        chunks = chunker.chunk_articles(articles)
        
        assert len(chunks) >= 2
        assert all(c.chunk_type == "article" for c in chunks)
        assert all(c.version == "test" for c in chunks)
    
    def test_chunk_metadata(self):
        """测试chunk元数据"""
        parser = LawParser()
        content = """
第四百六十三条 本编调整因合同产生的民事法律关系。
"""
        articles = parser.parse_law_content(content, "民法典")
        
        chunker = StructuredLawChunker()
        chunks = chunker.chunk_articles(articles)
        
        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.article_id == "民法典第463条"
        assert chunk.article_number == "463"
        assert chunk.law_name == "民法典"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
