"""法规库精确条号关联适配器测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.services.law_relation_lookup import build_collection_law_lookup


def test_collection_lookup_uses_exact_law_name_and_article_number():
    """只接受法规名和规范化条号均一致的 Chroma 元数据命中。"""
    calls = []

    class FakeCollection:
        def get(self, *, where, include):
            calls.append((where, include))
            return {
                "ids": ["chunk-10", "chunk-10-summary"],
                "metadatas": [
                    {"article_id": "中华人民共和国劳动合同法第10条"},
                    {"article_id": "中华人民共和国劳动合同法第10条"},
                ],
            }

    lookup = build_collection_law_lookup(FakeCollection())

    result = lookup("中华人民共和国劳动合同法", "10")

    assert calls == [
        (
            {
                "$and": [
                    {"law_name": "中华人民共和国劳动合同法"},
                    {"article_number": "10"},
                ]
            },
            ["metadatas"],
        )
    ]
    assert result == [
        {
            "target_id": "中华人民共和国劳动合同法第10条",
            "target_type": "law_article",
        },
        {
            "target_id": "中华人民共和国劳动合同法第10条",
            "target_type": "law_article",
        },
    ]
