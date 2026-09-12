"""保留来源位置的通用文本分块器。"""

from typing import Any


class DocumentChunker:
    """按字符长度拆分每个来源段，避免 chunk 跨越来源位置。"""

    def chunk_segments(
        self,
        segments: list[dict[str, Any]],
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        step = chunk_size - chunk_overlap
        for segment in segments:
            text = str(segment.get("text", "")).strip()
            for start in range(0, len(text), step):
                content = text[start : start + chunk_size]
                if not content:
                    continue
                chunk = {"content": content}
                if "page" in segment:
                    chunk["page"] = segment["page"]
                if "paragraph" in segment:
                    chunk["paragraph"] = segment["paragraph"]
                chunks.append(chunk)
                if start + chunk_size >= len(text):
                    break
        return chunks
