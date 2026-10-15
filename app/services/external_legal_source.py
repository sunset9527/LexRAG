"""合规外部法律来源边界。

默认中国法律站点适配器为禁用状态；调用方必须显式提供获授权 URL 与用途，
任何访问失败都以结构化降级返回，绝不伪造为法律检索结果。
"""

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class ExternalSourceResult:
    source: str
    available: bool
    items: list[dict]
    reason: str | None = None


class ExternalLegalSource(Protocol):
    async def search(self, query: str) -> ExternalSourceResult: ...


class DisabledChineseLegalSource:
    def __init__(self, source: str, reason: str = "未配置获授权访问方式"):
        self.source = source
        self.reason = reason

    async def search(self, query: str) -> ExternalSourceResult:
        return ExternalSourceResult(self.source, False, [], self.reason)


class MediaWikiLegalConceptSource:
    source = "MediaWiki REST"

    async def search(self, query: str) -> ExternalSourceResult:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    "https://zh.wikipedia.org/w/rest.php/v1/search/page",
                    params={"q": query, "limit": 5},
                    headers={"User-Agent": "LexRAG/3.0 local demo"},
                )
                response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            return ExternalSourceResult(
                self.source, False, [], f"external_request_failed:{type(exc).__name__}"
            )
        return ExternalSourceResult(
            self.source,
            True,
            [
                {
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "url": f"https://zh.wikipedia.org/wiki/{item.get('key', '')}",
                    "authority": "non_authoritative",
                }
                for item in response.json().get("pages", [])
            ],
        )
