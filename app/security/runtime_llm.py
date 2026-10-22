"""Validation and transport bounds for request-scoped LLM providers."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

from config import Settings

_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_ALLOWED_PORTS = {80, 443}


@dataclass(frozen=True)
class RuntimeLLMConfig:
    base_url: str
    model: str
    timeout_seconds: int
    max_output_tokens: int
    max_retries: int


def _default_resolver(host: str, port: int) -> Iterable[str]:
    return {
        item[4][0]
        for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if item[4]
    }


def _canonical_url(value: str) -> tuple[str, SplitResult, int]:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Base URL 必须是有效的 HTTP(S) 地址")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Base URL 不得包含凭据")
    if parsed.query or parsed.fragment:
        raise ValueError("Base URL 不得包含查询参数或片段")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValueError("Base URL 端口无效") from exc
    if port not in _ALLOWED_PORTS:
        raise ValueError("Base URL 使用了不允许的端口")

    host = parsed.hostname.encode("idna").decode("ascii").lower()
    host_display = f"[{host}]" if ":" in host else host
    netloc = host_display if port == (443 if parsed.scheme.lower() == "https" else 80) else f"{host_display}:{port}"
    path = parsed.path.rstrip("/")
    canonical = urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))
    return canonical, parsed._replace(scheme=parsed.scheme.lower(), netloc=netloc), port


class RuntimeLLMPolicy:
    """Fail-closed policy for BYOK endpoint and model selection."""

    def __init__(
        self,
        settings: Settings,
        *,
        resolver: Callable[[str, int], Iterable[str]] = _default_resolver,
    ) -> None:
        self.settings = settings
        self.resolver = resolver
        self.trusted_urls = {
            _canonical_url(item)[0]
            for item in settings.runtime_llm_trusted_base_urls.split(",")
            if item.strip()
        }

    def validate(
        self,
        *,
        base_url: str,
        model: str,
        allow_custom: bool,
    ) -> RuntimeLLMConfig:
        canonical, parsed, port = _canonical_url(base_url)
        if not _MODEL_NAME.fullmatch(model):
            raise ValueError("模型名称格式无效")

        trusted = canonical in self.trusted_urls
        if not trusted and self.settings.app_mode == "production" and not allow_custom:
            raise ValueError("当前用户使用自定义模型地址的权限不足")
        if not trusted and self.settings.app_mode == "production" and parsed.scheme != "https":
            raise ValueError("生产环境的自定义模型地址必须使用 HTTPS")

        host = parsed.hostname or ""
        if host.lower() == "localhost":
            raise ValueError("模型地址必须解析到公网地址")
        try:
            literal = ipaddress.ip_address(host)
            addresses = (str(literal),)
        except ValueError:
            try:
                addresses = tuple(self.resolver(host, port))
            except OSError as exc:
                raise ValueError("模型地址 DNS 解析失败") from exc
        if not addresses:
            raise ValueError("模型地址 DNS 解析失败")
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ValueError("模型地址 DNS 结果无效") from exc
            if not parsed_address.is_global:
                raise ValueError("模型地址必须解析到公网地址")

        return RuntimeLLMConfig(
            base_url=canonical,
            model=model,
            timeout_seconds=self.settings.runtime_llm_timeout_seconds,
            max_output_tokens=self.settings.runtime_llm_max_output_tokens,
            max_retries=self.settings.runtime_llm_max_retries,
        )

    def build_http_clients(self) -> tuple[httpx.Client, httpx.AsyncClient]:
        timeout = httpx.Timeout(self.settings.runtime_llm_timeout_seconds)
        limits = httpx.Limits(
            max_connections=self.settings.runtime_llm_max_concurrency,
            max_keepalive_connections=self.settings.runtime_llm_max_concurrency,
        )
        return (
            httpx.Client(timeout=timeout, limits=limits, follow_redirects=False),
            httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False),
        )
