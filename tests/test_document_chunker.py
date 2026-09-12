"""通用文档分块测试。"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.ingestion.document_chunker import DocumentChunker


def test_chunker_keeps_source_position_and_overlap():
    """一个长段落被切分后，每块应保留页码，并按配置重叠。"""
    chunks = DocumentChunker().chunk_segments(
        [{"text": "abcdefghij", "page": 3}], chunk_size=6, chunk_overlap=2
    )

    assert chunks == [
        {"content": "abcdef", "page": 3},
        {"content": "efghij", "page": 3},
    ]
