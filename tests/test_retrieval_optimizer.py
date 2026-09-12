# -*- coding: utf-8 -*-
"""本轮检索优化（P0）的离线单元测试：retrieval_optimizer + fusion weights

不依赖 LLM / 向量库 / 网络，秒级可跑：
    python -m pytest tests/test_retrieval_optimizer.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrieval import retrieval_optimizer as ropt
from src.retrieval.fusion import reciprocal_rank_fusion


class TestCn2Num:
    def test_arabic(self):
        assert ropt.cn2num("188") == "188"

    def test_plain(self):
        assert ropt.cn2num("一百八十八") == "188"

    def test_thousand(self):
        assert ropt.cn2num("一千二百六十") == "1260"

    def test_ten(self):
        assert ropt.cn2num("十") == "10"

    def test_twenty(self):
        assert ropt.cn2num("二十") == "20"


class TestExtractArticleNums:
    def test_single(self):
        assert ropt.extract_article_nums("民法典第188条是什么？") == ["188"]

    def test_multiple(self):
        assert ropt.extract_article_nums("第1134条和第1135条") == ["1134", "1135"]

    def test_chinese(self):
        assert ropt.extract_article_nums("第一百四十二条") == ["142"]

    def test_none(self):
        assert ropt.extract_article_nums("成年人多少岁？") == []


class TestRrfWeights:
    def test_number_query_bm25_heavy(self):
        wb, wv = ropt.rrf_weights("民法典第188条是什么？")
        assert wb == 1.4 and wv == 0.6

    def test_semantic_query_vector_heavy(self):
        wb, wv = ropt.rrf_weights("遗嘱有哪些法定形式？")
        assert wb == 0.7 and wv == 1.3

    def test_plain_equal(self):
        wb, wv = ropt.rrf_weights("定金合同")
        assert wb == 1.0 and wv == 1.0


class TestExactArticleBoost:
    def _mk(self):
        info = {
            "a1": {"article": "188", "chapter": "x", "content": "", "full": ""},
            "a2": {"article": "17", "chapter": "y", "content": "", "full": ""},
        }
        ranked = [("a2", 0.5), ("a1", 0.4)]
        return ranked, info

    def test_boost_rank1(self):
        ranked, info = self._mk()
        out = ropt.exact_article_boost(ranked, info, "第188条如何规定？")
        assert out[0][0] == "a1"          # 被置顶
        assert out[0][1] == 1e9

    def test_no_boost_without_number(self):
        ranked, info = self._mk()
        out = ropt.exact_article_boost(ranked, info, "成年人多少岁？")
        assert out == ranked              # 无条号不动


class TestChapterWindowAggregate:
    def test_window_covers_neighbors(self):
        chapter_map = {"第三章": {1133, 1134, 1135, 1136, 1137, 1138, 1139, 1140},
                       "第二章": {100}}
        out = ropt.chapter_window_aggregate(["1135", "1137"], chapter_map, window=2)
        assert 1134 in out and 1139 in out   # ±2 窗口覆盖相邻条
        assert 1133 in out                   # 窗口下边界（1135-2）
        assert 1132 not in out               # 超出下窗口
        assert 1140 not in out               # 超出上窗口（1137+2=1139）
        assert 100 not in out                # 不同章节

    def test_cross_chapter(self):
        chapter_map = {"第五章": {1098, 1099}, "第四章": {1000, 1001}}
        out = ropt.chapter_window_aggregate(["1098"], chapter_map, window=2)
        assert 1099 in out
        assert 1000 not in out


class TestFusionWeights:
    def _docs(self, name):
        return [{"doc_id": f"{name}_{i}", "content": f"{name}{i}", "score": 1.0,
                 "metadata": {"article_number": str(i)}} for i in range(3)]

    def test_equal_weights_default(self):
        r = reciprocal_rank_fusion([self._docs("a"), self._docs("b")], k=60)
        assert len(r) == 6

    def test_weight_changes_order(self):
        # 一路权重放大后，其 doc 应排到前面
        docs_a = self._docs("a")
        docs_b = self._docs("b")
        r_eq = reciprocal_rank_fusion([docs_a, docs_b], k=60)
        r_w = reciprocal_rank_fusion([docs_a, docs_b], k=60, weights=[10.0, 0.1])
        top_eq = [x.doc_id for x in r_eq[:2]]
        top_w = [x.doc_id for x in r_w[:2]]
        assert top_eq != top_w                    # 加权确实改变排序
        assert top_w[0].startswith("a_")          # 权重大的那路 doc 靠前

    def test_weights_short_list(self):
        # 权重列表短于检索路数时，缺省按 1.0
        r = reciprocal_rank_fusion([self._docs("a"), self._docs("b")], k=60, weights=[2.0])
        assert len(r) == 6
