# -*- coding: utf-8 -*-
"""引用图增强召回 + 检索/生成字段分离 的离线单元测试（不调 LLM / 不依赖向量库）

覆盖：
- expand_by_references：命中条文有引用 -> 扩展；无引用 -> 不扩展；
  max_hops / max_add 生效；双向扩展（被引条文命中时找回引用方）；
  只补充知识库中存在的条文
- compress_context_simple：超长截断、保留条号、首尾保留、不超 max_chars
- format_grouped_context：引用相关标注 + 摘要接入（向后兼容）

秒级可跑：python -m pytest tests/test_retrieval_expansion.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrieval import retrieval_optimizer as ropt
from src.retrieval.context_compressor import compress_context_simple


def _lookup(pairs):
    """{条号int: 条文内容} 构建"""
    return {int(a): c for a, c in pairs}


class TestParseReferencedArticles:
    """metadata.referenced_articles 字符串解析"""

    def test_list_string(self):
        assert ropt.parse_referenced_articles("['第395条']") == {"395"}

    def test_multi_and_chinese_numeral(self):
        assert ropt.parse_referenced_articles("['第395条', '第一百四十二条']") == {"395", "142"}

    def test_empty(self):
        assert ropt.parse_referenced_articles("") == set()
        assert ropt.parse_referenced_articles("[]") == set()
        assert ropt.parse_referenced_articles(None) == set()

    def test_malformed_fallback_regex(self):
        # 非合法列表字符串 -> 回退正则提取
        assert ropt.parse_referenced_articles("依据本法第395条") == {"395"}

    def test_real_list_object(self):
        assert ropt.parse_referenced_articles(["第396条"]) == {"396"}


class TestExpandByReferences:
    """引用图增强召回"""

    def test_hit_with_reference_expands(self):
        """命中条文有引用 -> 扩展出被引条号"""
        refs = {"586": {"587"}}
        out = ropt.expand_by_references(["586"], _lookup([(586, "a"), (587, "b")]), refs)
        assert out == {587}

    def test_no_reference_no_expansion(self):
        """无引用 -> 不扩展（空引用表 / 空 references_map / None）"""
        refs = {"586": set()}
        lookup = _lookup([(586, "a")])
        assert ropt.expand_by_references(["586"], lookup, refs) == set()
        assert ropt.expand_by_references(["586"], lookup, None) == set()

    def test_reverse_direction(self):
        """被引条文命中 -> 反向扩展出引用它的条文（如 第402条引用第395条）"""
        refs = {"402": {"395"}}
        out = ropt.expand_by_references(["395"], _lookup([(395, "a"), (402, "b")]), refs)
        assert out == {402}

    def test_max_hops(self):
        """max_hops 生效：A->B->C，1 跳只有 B，2 跳才有 C"""
        refs = {"100": {"101"}, "101": {"102"}}
        lookup = _lookup([(100, "a"), (101, "b"), (102, "c")])
        assert ropt.expand_by_references(["100"], lookup, refs, max_hops=1) == {101}
        assert ropt.expand_by_references(["100"], lookup, refs, max_hops=2) == {101, 102}

    def test_max_add(self):
        """max_add 生效：邻居超过上限时只取前 N 条（按条号升序，输出确定性）"""
        refs = {"100": {"101", "102", "103", "104"}}
        lookup = _lookup([(100, "a"), (101, "b"), (102, "c"), (103, "d"), (104, "e")])
        out = ropt.expand_by_references(["100"], lookup, refs, max_add=2)
        assert len(out) == 2 and out == {101, 102}

    def test_only_existing_articles(self):
        """只补充知识库中存在的条文（9999 不在库 -> 忽略）"""
        refs = {"100": {"101", "9999"}}
        out = ropt.expand_by_references(["100"], _lookup([(100, "a"), (101, "b")]), refs)
        assert out == {101}

    def test_seed_not_expanded_again(self):
        """扩展结果不含命中条文本身（循环引用安全）"""
        refs = {"586": {"587"}, "587": {"586"}}
        out = ropt.expand_by_references(["586"], _lookup([(586, "a"), (587, "b")]), refs)
        assert out == {587}


class TestCompressContextSimple:
    """无 LLM 轻量摘要（检索/生成字段分离）"""

    LONG = "第一千一百三十五条　" + "代书遗嘱应当有两个以上见证人在场见证。" * 60

    def test_short_kept_unchanged(self):
        t = "第一千一百三十五条　代书遗嘱应当有两个以上见证人在场见证。"
        assert compress_context_simple(t, max_chars=500) == t

    def test_at_boundary_unchanged(self):
        t = "x" * 500
        assert compress_context_simple(t, max_chars=500) == t

    def test_long_truncated_with_marker(self):
        out = compress_context_simple(self.LONG, max_chars=500)
        assert len(out) <= 500
        assert "中间省略" in out

    def test_keeps_article_number(self):
        """截断后仍保留条号（条文开头）"""
        out = compress_context_simple(self.LONG, max_chars=200)
        assert out.startswith("第一千一百三十五条")

    def test_keeps_head_and_tail(self):
        """首尾保留：开头关键句 + 末尾仍在"""
        head = "第一千一百三十五条　代书遗嘱应当有两个以上见证人在场见证。"
        tail = "注明年、月、日。"
        text = head + ("中间内容" * 200) + tail
        out = compress_context_simple(text, max_chars=300)
        assert out.startswith(head[:20])
        assert out.endswith(tail)
        assert len(out) <= 300

    def test_never_exceeds_max_chars(self):
        for cap in (50, 100, 300, 500):
            assert len(compress_context_simple("法" * 3000, max_chars=cap)) <= cap

    def test_empty(self):
        assert compress_context_simple("", 500) == ""
        assert compress_context_simple(None, 500) == ""


class TestFormatGroupedContext:
    """聚合上下文格式化：引用相关标注 + 摘要接入"""

    def test_reference_annotation(self):
        """引用扩展补充的条号在上下文中标注「引用相关」"""
        lookup = {395: "可抵押财产范围条文", 402: "抵押登记条文"}
        ctx = ropt.format_grouped_context(
            {395, 402}, lookup, expanded_articles={395}
        )
        assert "第395条·引用相关" in ctx
        assert "第402条】" in ctx  # 命中条文不加标注

    def test_summary_applied_per_article(self):
        """每条内容过轻量摘要：单条正文不超过 max_chars_per_article"""
        long_text = "长" * 1000
        lookup = {586: long_text, 588: long_text}
        ctx = ropt.format_grouped_context({586, 588}, lookup, max_chars_per_article=300)
        for part in ctx.split("\n\n"):
            body = part.split("】\n", 1)[1]
            assert len(body) <= 300

    def test_backward_compatible_no_new_args(self):
        """不传新参数时输出与 P0 完全一致（无摘要、无标注）"""
        lookup = {586: "条文内容"}
        assert ropt.format_grouped_context({586}, lookup) == "【中华人民共和国民法典第586条】\n条文内容"
