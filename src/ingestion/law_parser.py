"""
法律文档结构化解析器

解析法律文档的层级结构（编→章→节→条→款→项）
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LawArticle:
    """法律条文数据结构"""
    article_id: str                    # 条文唯一标识符，如 "民法典第143条"
    law_name: str                      # 法律名称，如 "中华人民共和国民法典"
    chapter: str                       # 所属章
    article_number: str                # 条号，如 "143"
    content: str                       # 条文正文
    section: Optional[str] = None      # 所属节
    paragraphs: List[str] = field(default_factory=list)  # 款/项列表
    effective_date: Optional[str] = None  # 生效日期
    latest_amendment: Optional[str] = None  # 最近修订日期
    is_amended: bool = False           # 是否经过修订
    references: List[str] = field(default_factory=list)  # 引用的其他法条
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "article_id": self.article_id,
            "law_name": self.law_name,
            "chapter": self.chapter,
            "section": self.section,
            "article_number": self.article_number,
            "content": self.content,
            "paragraphs": self.paragraphs,
            "effective_date": self.effective_date,
            "latest_amendment": self.latest_amendment,
            "is_amended": self.is_amended,
            "references": self.references,
        }


class LawParser:
    """
    法律文档结构化解析器
    
    支持解析以下层级结构：
    - 编 (Part)
    - 章 (Chapter)
    - 节 (Section)
    - 条 (Article)
    - 款 (Paragraph)
    - 项 (Item)
    """
    
    # 法条编号的正则表达式
    ARTICLE_PATTERN = re.compile(
        r'第([一二三四五六七八九十百千零\d]+)条'
    )
    
    # 款/项的正则表达式
    PARAGRAPH_PATTERN = re.compile(r'^（[一二三四五六七八九十]+）|^(\d+)、|^[①②③④⑤⑥⑦⑧⑨⑩]')
    
    # 法条引用正则表达式（如：依据本法第十条、参照本法第二十条）
    REFERENCE_PATTERN = re.compile(
        r'(?:依据|依照|根据|参照|适用|比照本章)?本法(?:第)?([零一二三四五六七八九十百千\d]+)条'
    )
    
    def __init__(self):
        """初始化解析器"""
        self.current_context = {
            "law_name": "",
            "chapter": "",
            "section": "",
        }
        self.articles: List[LawArticle] = []
    
    def parse_law_file(self, file_path: str | Path) -> List[LawArticle]:
        """
        解析法律文件
        
        Args:
            file_path: 法律文件路径
            
        Returns:
            解析出的法律条文列表
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"法律文件不存在: {file_path}")
        
        logger.info(f"开始解析法律文件: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 更新法律名称
        self.current_context["law_name"] = self._extract_law_name(content)
        
        # 按行解析
        lines = content.split('\n')
        current_article = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检测章标题
            if self._is_chapter_title(line):
                self.current_context["chapter"] = self._extract_chapter_title(line)
                logger.debug(f"解析到章: {self.current_context['chapter']}")
            
            # 检测节标题
            elif self._is_section_title(line):
                self.current_context["section"] = self._extract_section_title(line)
                logger.debug(f"解析到节: {self.current_context['section']}")
            
            # 检测法条
            elif self._is_article_start(line):
                # 保存前一个法条
                if current_article:
                    self.articles.append(current_article)
                
                # 开始新法条
                current_article = self._parse_article(line)
                current_article.chapter = self.current_context["chapter"]
                current_article.section = self.current_context["section"]
                current_article.law_name = self.current_context["law_name"]
                
                # 提取引用
                current_article.references = self._extract_references(line)
            
            # 法条内容续写
            elif current_article:
                current_article.content += '\n' + line
                
                # 检查是否有款/项
                if self.PARAGRAPH_PATTERN.match(line):
                    current_article.paragraphs.append(line)
        
        # 保存最后一个法条
        if current_article:
            self.articles.append(current_article)
        
        logger.info(f"解析完成，共提取 {len(self.articles)} 条法律条文")
        return self.articles
    
    def parse_law_content(self, content: str, law_name: str = "法律") -> List[LawArticle]:
        """
        解析法律内容文本
        
        Args:
            content: 法律文本内容
            law_name: 法律名称
            
        Returns:
            解析出的法律条文列表
        """
        self.current_context["law_name"] = law_name
        self.articles = []
        
        lines = content.split('\n')
        current_article = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if self._is_chapter_title(line):
                self.current_context["chapter"] = self._extract_chapter_title(line)
            elif self._is_section_title(line):
                self.current_context["section"] = self._extract_section_title(line)
            elif self._is_article_start(line):
                if current_article:
                    self.articles.append(current_article)
                current_article = self._parse_article(line)
                current_article.chapter = self.current_context["chapter"]
                current_article.section = self.current_context["section"]
                current_article.law_name = law_name
                current_article.references = self._extract_references(line)
            elif current_article:
                current_article.content += '\n' + line
                if self.PARAGRAPH_PATTERN.match(line):
                    current_article.paragraphs.append(line)
        
        if current_article:
            self.articles.append(current_article)
        
        return self.articles
    
    def _extract_law_name(self, content: str) -> str:
        """提取法律名称"""
        lines = content.split('\n')
        for line in lines[:10]:  # 只检查前10行
            line = line.strip()
            if line and not self._is_chapter_title(line) and not self._is_section_title(line):
                # 通常法律名称在文件开头
                if any(keyword in line for keyword in ["法", "条例", "规定", "办法"]):
                    return line
        return "法律"
    
    def _is_chapter_title(self, line: str) -> bool:
        """判断是否为章标题"""
        return line.startswith("第") and "章" in line and len(line) < 50
    
    def _extract_chapter_title(self, line: str) -> str:
        """提取章标题"""
        return line.strip()
    
    def _is_section_title(self, line: str) -> bool:
        """判断是否为节标题"""
        return line.startswith("第") and "节" in line and len(line) < 50
    
    def _extract_section_title(self, line: str) -> str:
        """提取节标题"""
        return line.strip()
    
    def _is_article_start(self, line: str) -> bool:
        """判断是否法条开始"""
        return bool(self.ARTICLE_PATTERN.search(line))
    
    def _parse_article(self, line: str) -> LawArticle:
        """解析法条"""
        match = self.ARTICLE_PATTERN.search(line)
        article_number = self._convert_chinese_number(match.group(1)) if match else "0"
        
        article_id = f"{self.current_context['law_name']}第{article_number}条"
        
        return LawArticle(
            article_id=article_id,
            law_name=self.current_context["law_name"],
            chapter=self.current_context["chapter"],
            section=self.current_context["section"],
            article_number=article_number,
            content=line,
        )
    
    def _convert_chinese_number(self, num_str: str) -> str:
        """将中文数字转换为阿拉伯数字"""
        chinese_map = {
            '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
            '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
            '十': '10', '百': '100', '千': '1000'
        }
        
        # 如果是纯数字
        try:
            return str(int(num_str))
        except ValueError:
            pass
        
        # 转换中文数字
        result = 0
        temp = 0
        for char in num_str:
            if char == '万':
                result = (result + temp) * 10000
                temp = 0
            elif char == '亿':
                result = (result + temp) * 100000000
                temp = 0
            elif char in chinese_map:
                val = int(chinese_map[char])
                if val >= 10:
                    temp = temp * val if temp else val
                else:
                    temp += val
        result += temp
        return str(result) if result else num_str
    
    def _extract_references(self, text: str) -> List[str]:
        """提取法条引用"""
        references = []
        for match in self.REFERENCE_PATTERN.finditer(text):
            ref_num = match.group(1)
            ref_num_converted = self._convert_chinese_number(ref_num)
            references.append(f"第{ref_num_converted}条")
        return references
    
    def get_article_by_number(self, article_number: str) -> Optional[LawArticle]:
        """根据条号获取法条"""
        for article in self.articles:
            if article.article_number == article_number:
                return article
        return None
    
    def export_to_dicts(self) -> List[Dict[str, Any]]:
        """导出为字典列表"""
        return [article.to_dict() for article in self.articles]
