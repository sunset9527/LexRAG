# -*- coding: utf-8 -*-
"""
检索优化器：LexRAG 检索优化（对应滴普科技 HR 建议「召回颗粒度 + 重排 + 上下文瘦身」）

1. 精确条号置顶（exact_article_boost）
   - query 含「第X条」时，直接将该条置为 rank1（metadata 精确匹配，重排保险）
2. RRF 动态加权（rrf_weights）
   - 编号/术语类 query：BM25 权重 1.4，向量 0.6（关键词精确匹配优先）
   - 语义类 query（什么/哪些/如何/是否）：向量权重 1.3，BM25 0.7（语义理解优先）
3. 条款组聚合（chapter_window_aggregate）
   - 命中多条时按「章节 ±N 条窗口」聚合为一组规则返回
   - 解决单条切片对跨条款综合题（如「遗嘱有哪些法定形式」）召回不全的问题
4. 引用图增强召回（expand_by_references）
   - 命中条文沿 referenced_articles 引用边 BFS 扩展（双向，默认 1 跳、最多 3 条）
   - 例：第402条引用第395条，命中 402 自动带回 395（可抵押财产范围）
5. 检索/生成字段分离（compress_context_simple + format_grouped_context）
   - 检索用短 chunk（page_content「条文内容」），生成上下文每条先过无 LLM 轻量摘要
   - 单条 ≤ max_chars 硬上限，控制生成上下文长度（上下文瘦身）

评测实证（eval_retrieval_legal_v3.py，25+3 条 query，2026-08-04）：
  - 单条题 Hit@5 15/15（优化前后均为 100%，无回归）
  - 综合题检索 Coverage@5：73% -> 77%（RRF 加权）
  - 综合题聚合 Coverage：-> 100%（10/10 全命中，5 道题 +33~50pt）
  - 编号题置顶 Hit@1：2/3 -> 3/3

补充（v2.1，2026-08-04，eval_retrieval_legal_v4.py + test_retriever_optimized.py）：
  - 28 条 query 指标无回归（单条 Hit@5 15/15，编号置顶 Hit@1 3/3，综合聚合 Coverage 100% 10/10）
  - 引用图增强召回实测：命中 402 -> 扩展被引的 395；命中 395 -> 反向扩展引用它的 402，
    生成上下文标注「·引用相关」（单元测试另覆盖 max_hops/max_add/循环引用安全）
  - 检索/生成字段分离实测：生成上下文单条 ≤500 字硬上限，长条文场景 2356 -> 2100 字（max=200/条）
"""
import ast
import logging
import re
from typing import Dict, List, Tuple, Set, Any, Optional

logger = logging.getLogger(__name__)

# ==================== 中文数字转换（与 law_parser 保持一致） ====================
DIGITS = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
          '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
UNITS = {'十': 10, '百': 100, '千': 1000, '万': 10000, '亿': 100000000}


def cn2num(num_str: str) -> str:
    """中文数字 -> 阿拉伯数字字符串（一千二百六十 -> 1260）"""
    try:
        return str(int(num_str))
    except ValueError:
        pass
    result = 0
    temp = 0
    for ch in num_str:
        if ch in DIGITS:
            temp = DIGITS[ch]
        elif ch in UNITS:
            unit = UNITS[ch]
            if unit >= 10000:
                result = (result + temp) * unit
                temp = 0
            else:
                result += (temp if temp else 1) * unit
                temp = 0
    result += temp
    return str(result) if result else num_str


ARTICLE_PATTERN = re.compile(r'第([一二三四五六七八九十百千零\d]+)条')


def extract_article_nums(query: str) -> List[str]:
    """从 query 提取所有「第X条」条号（如 第188条 -> ['188']）"""
    return [cn2num(m.group(1)) for m in ARTICLE_PATTERN.finditer(query)]


# ==================== RRF 动态加权 ====================
def is_number_query(query: str) -> bool:
    """编号类：query 带具体条号"""
    return bool(ARTICLE_PATTERN.search(query))


def is_semantic_query(query: str) -> bool:
    """语义类：问「什么/哪些/如何/是否/能否」等"""
    return any(k in query for k in ['什么', '哪些', '如何', '是否', '能否',
                                    '怎样', '怎么办', '吗', '吗？'])


def rrf_weights(query: str) -> Tuple[float, float]:
    """返回 (BM25 权重, 向量权重)"""
    if is_number_query(query):
        return 1.4, 0.6
    if is_semantic_query(query):
        return 0.7, 1.3
    return 1.0, 1.0


# ==================== 精确条号置顶 ====================
def exact_article_boost(
    ranked: List[Tuple[str, float]],
    info: Dict[str, Dict[str, Any]],
    query: str
) -> List[Tuple[str, float]]:
    """
    精确条号置顶：query 提到第X条 -> 该条文档直接置顶 rank1。
    ranked: [(chunk_id, score)] 已按分数降序
    info: {chunk_id: {article, content, chapter, full}}
    """
    nums = extract_article_nums(query)
    if not nums:
        return ranked
    for num in nums:
        for key, val in info.items():
            if val.get("article") == num:
                return [(key, 1e9)] + [x for x in ranked if x[0] != key]
    return ranked


# ==================== 条款组聚合 ====================
def build_chapter_article_map(metadatas: List[Dict[str, Any]]) -> Dict[str, Set[int]]:
    """从全部 chunk metadata 构建 章节 -> 条号集合 映射"""
    chapter_map: Dict[str, Set[int]] = {}
    for md in metadatas:
        ch = str(md.get("chapter", ""))
        an = str(md.get("article_number", ""))
        if ch and an.isdigit():
            chapter_map.setdefault(ch, set()).add(int(an))
    return chapter_map


def find_chapter(article_num: int, chapter_map: Dict[str, Set[int]]) -> Optional[str]:
    """查找条号所属章节"""
    for ch, arts in chapter_map.items():
        if article_num in arts:
            return ch
    return None


def chapter_window_aggregate(
    article_numbers: List[str],
    chapter_map: Dict[str, Set[int]],
    window: int = 2
) -> Set[int]:
    """
    章节窗口聚合：命中条号 -> 所在章节 ±window 条号窗口 -> 并集返回。
    返回聚合后的条号集合（作为生成上下文的一组规则）。
    """
    covered: Set[int] = set()
    for a in article_numbers:
        if not a.isdigit():
            continue
        an = int(a)
        ch = find_chapter(an, chapter_map)
        if ch:
            covered |= {x for x in chapter_map[ch] if an - window <= x <= an + window}
    return covered


# ==================== 引用图增强召回 ====================
def parse_referenced_articles(ref_str: Any) -> Set[str]:
    """
    解析 metadata.referenced_articles 为阿拉伯数字条号集合。

    入库格式为字符串化的列表（如 "['第395条','第一百四十二条']"），
    优先 ast.literal_eval 还原，失败时回退正则提取；中文数字统一转阿拉伯数字。
    """
    if not ref_str:
        return set()
    items: List[str] = []
    if isinstance(ref_str, (list, tuple)):
        items = [str(x) for x in ref_str]
    elif isinstance(ref_str, str):
        try:
            parsed = ast.literal_eval(ref_str)
            if isinstance(parsed, (list, tuple)):
                items = [str(x) for x in parsed]
        except (ValueError, SyntaxError):
            pass
        if not items:
            # 回退：直接从字符串里抓所有「第X条」
            items = [m.group(0) for m in ARTICLE_PATTERN.finditer(ref_str)]
    nums: Set[str] = set()
    for it in items:
        m = ARTICLE_PATTERN.search(it)
        if m:
            nums.add(cn2num(m.group(1)))
    return nums


def build_references_map(metadatas: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
    """
    从全部 chunk metadata 构建 条号 -> 被引用条号集合 映射（多 chunk 取并集）。

    与 build_chapter_article_map 同源（整库 metadata 懒加载一次），
    作为 expand_by_references 的引用图边集合（等价于 law_graph 的 cites 边）。
    """
    ref_map: Dict[str, Set[str]] = {}
    for md in metadatas:
        an = str(md.get("article_number", ""))
        if not an.isdigit():
            continue
        refs = parse_referenced_articles(md.get("referenced_articles", ""))
        if refs:
            ref_map.setdefault(an, set()).update(refs)
    return ref_map


def _in_lookup(num_str: str, article_lookup: Dict[int, str]) -> bool:
    """条号是否存在于知识库（兼容 int/str 键）"""
    if num_str in article_lookup:
        return True
    try:
        return int(num_str) in article_lookup
    except (TypeError, ValueError):
        return False


def expand_by_references(
    article_numbers: List[str],
    article_lookup: Dict[int, str],
    references_map: Optional[Dict[str, Set[str]]] = None,
    max_hops: int = 1,
    max_add: int = 3,
) -> Set[int]:
    """
    引用图增强召回：对检索命中的条文，沿引用边做受限 BFS 扩展。

    边来源：metadata.referenced_articles（如 第402条 -> ['第395条']），
    双向扩展（命中条文引用他条 / 他条引用命中条文），最多 max_hops 跳、
    最多补充 max_add 条，且只保留知识库中真实存在的条文。
    与 graph_retriever 的 BFS 同构，此处直接用 metadata 边，无需预构建图谱。

    Args:
        article_numbers: 检索命中的条号列表（字符串或数字均可）
        article_lookup: {条号(int): 条文内容}，用于过滤不存在的条号
        references_map: {条号: 被引用条号集合}，为空时不做扩展
        max_hops: 最大扩展跳数（1 = 只取直接引用邻居）
        max_add: 最多补充的条数（防止上下文膨胀）

    Returns:
        补充条号集合（Set[int]），可与章节窗口聚合结果直接取并集
    """
    if not references_map:
        return set()
    seeds = {str(a) for a in article_numbers}
    # 反向索引：被引用条号 -> 引用它的条号（命中被引条文时找回引用方）
    reverse: Dict[str, Set[str]] = {}
    for src, targets in references_map.items():
        for t in targets:
            reverse.setdefault(t, set()).add(src)
    expanded: Set[int] = set()
    frontier: Set[str] = seeds
    for _hop in range(max_hops):
        if len(expanded) >= max_add:
            break
        candidates: Set[str] = set()
        for a in frontier:
            for nb in references_map.get(a, set()) | reverse.get(a, set()):
                if nb in seeds or nb in candidates:
                    continue
                if not _in_lookup(nb, article_lookup):
                    continue
                candidates.add(nb)
        # 同一跳内按条号升序取，保证输出确定性，最多补满 max_add
        ordered = sorted(candidates, key=lambda x: int(x) if x.isdigit() else 0)
        for nb in ordered:
            if len(expanded) >= max_add:
                break
            expanded.add(int(nb))
        frontier = candidates
    return expanded


def format_grouped_context(
    grouped_articles: Set[int],
    article_lookup: Dict[int, str],
    law_name: str = "中华人民共和国民法典",
    max_chars_per_article: Optional[int] = None,
    expanded_articles: Optional[Set[int]] = None,
) -> str:
    """
    将聚合后的条号集合格式化为生成上下文文本。
    article_lookup: {条号: 条文内容}
    max_chars_per_article: 每条条文内容最大字符数（超过则走无 LLM 轻量摘要，
        实现「检索/生成字段分离」：检索用全文命中、生成用摘要，控制上下文长度）
    expanded_articles: 引用图扩展补充的条号集合（上下文标注「·引用相关」）
    """
    if not grouped_articles:
        return ""
    expanded = expanded_articles or set()
    parts = []
    for an in sorted(grouped_articles):
        content = article_lookup.get(an, "")
        if not content:
            continue
        if max_chars_per_article:
            from .context_compressor import compress_context_simple
            content = compress_context_simple(content, max_chars=max_chars_per_article)
        tag = "·引用相关" if an in expanded else ""
        parts.append(f"【{law_name}第{an}条{tag}】\n{content}")
    return "\n\n".join(parts)
