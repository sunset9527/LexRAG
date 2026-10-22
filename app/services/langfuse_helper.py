"""
Langfuse LLM 可观测性集成

create_llm() 统一工厂函数，自动注入 Langfuse CallbackHandler
用于追踪 Token 消耗、延迟、成本和调用链
"""

import logging

from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI

from app.security.runtime_llm import RuntimeLLMPolicy
from config import settings

logger = logging.getLogger(__name__)

# 模块级 Langfuse handler 缓存
_langfuse_handler: BaseCallbackHandler | None = None


def _init_langfuse_handler() -> BaseCallbackHandler | None:
    """
    初始化 Langfuse CallbackHandler

    仅在配置了 Langfuse 密钥且成功导入 langfuse 包时启用
    """
    global _langfuse_handler

    if _langfuse_handler is not None:
        return _langfuse_handler

    if not settings.langfuse_enabled:
        logger.info("Langfuse 未启用（LANGFUSE_ENABLED=false）")
        return None

    # 检查必要配置
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning(
            "Langfuse 配置不完整（缺少 LANGFUSE_PUBLIC_KEY 或 LANGFUSE_SECRET_KEY），"
            "可观测性已禁用。如需启用，请在 .env 中配置这些变量。"
        )
        return None

    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            release=f"lexrag-{settings.langfuse_release}",
        )
        _langfuse_handler = handler
        logger.info(f"Langfuse 可观测性已启用 (host={settings.langfuse_host})")
        return handler

    except ImportError:
        logger.warning("langfuse 包未安装，可观测性不可用。运行 pip install langfuse 安装。")
        return None
    except Exception as exc:
        logger.error("Langfuse 初始化失败 error_type=%s", type(exc).__name__)
        return None


def create_llm(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    temperature: float = 0.1,
    request_timeout: int | None = None,
    max_retries: int | None = None,
    enable_langfuse: bool = True,
) -> ChatOpenAI:
    """
    创建 LLM 实例的统一工厂函数

    自动注入 Langfuse CallbackHandler 用于可观测性追踪。

    用法：
        llm = create_llm(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )
        response = llm.invoke("你好")

    每次调用自动记录：
    - 输入/输出 Token 数
    - 调用延迟
    - 成本估算
    - 调用链追踪（parent/child span）

    Args:
        api_key: API 密钥（默认使用 settings.deepseek_api_key）
        base_url: API 基础 URL
        model: 模型名称
        temperature: 温度参数
        request_timeout: 请求超时秒数
        max_retries: 最大重试次数
        enable_langfuse: 是否启用 Langfuse 追踪

    Returns:
        配置好的 ChatOpenAI 实例
    """
    callbacks = []

    if enable_langfuse:
        handler = _init_langfuse_handler()
        if handler:
            callbacks.append(handler)

    # 允许 API Key 为空（运行时由前端传入用户自己的 Key）
    effective_key = api_key or settings.deepseek_api_key or "sk-placeholder"
    effective_base = base_url or settings.deepseek_base_url
    effective_model = model or settings.deepseek_model
    policy = RuntimeLLMPolicy(settings)
    http_client, http_async_client = policy.build_http_clients()

    llm = ChatOpenAI(
        api_key=effective_key,
        base_url=effective_base,
        model=effective_model,
        temperature=temperature,
        request_timeout=min(
            request_timeout or settings.runtime_llm_timeout_seconds,
            settings.runtime_llm_timeout_seconds,
        ),
        max_retries=min(
            settings.runtime_llm_max_retries if max_retries is None else max_retries,
            settings.runtime_llm_max_retries,
        ),
        max_tokens=settings.runtime_llm_max_output_tokens,
        http_client=http_client,
        http_async_client=http_async_client,
        callbacks=callbacks if callbacks else None,
    )

    return llm


def get_langfuse_handler() -> BaseCallbackHandler | None:
    """
    获取 Langfuse handler（供需要手动添加到 callbacks 的场景使用）

    用法：
        handler = get_langfuse_handler()
        if handler:
            result = chain.invoke(input, config={"callbacks": [handler]})
    """
    return _init_langfuse_handler()


def flush_langfuse():
    """
    刷新 Langfuse 缓冲区（在应用关闭前调用，确保数据不会丢失）

    用法（FastAPI lifespan）：
        @app.on_event("shutdown")
        def shutdown():
            flush_langfuse()
    """
    try:
        from langfuse import Langfuse

        if settings.langfuse_public_key and settings.langfuse_secret_key:
            client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            client.flush()
            logger.info("Langfuse 数据已刷新")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("Langfuse flush 失败 error_type=%s", type(exc).__name__)
