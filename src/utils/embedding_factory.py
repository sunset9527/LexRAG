"""
Embedding 工厂 — 统一创建 Embedding 实例

优先级：本地模型 -> 智谱AI API 回退
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 全局缓存，避免重复加载模型
_embedding_instance: Optional[object] = None
_embedding_source: str = "unknown"


def create_embeddings(
    model_path: str = "E:/huggingface/model",
    zhipuai_api_key: Optional[str] = None,
    zhipuai_model: str = "embedding-3",
) -> object:
    """
    创建 Embedding 实例

    优先加载本地 HuggingFace 模型，失败则回退到智谱AI API。

    Args:
        model_path: 本地模型目录路径
        zhipuai_api_key: 智谱AI API Key
        zhipuai_model: 智谱AI Embedding 模型名

    Returns:
        LangChain 兼容的 Embeddings 实例
    """
    global _embedding_instance, _embedding_source

    if _embedding_instance is not None:
        return _embedding_instance

    # ===== 方案 1: 本地 HuggingFace 模型 =====
    if os.path.isdir(model_path):
        # 检查是否有 sentence-transformers 模型文件
        config_path = os.path.join(model_path, "config_sentence_transformers.json")
        if os.path.isfile(config_path):
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings

                # 设置 HF 镜像（国内加速）
                if not os.environ.get("HF_ENDPOINT"):
                    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

                embeddings = HuggingFaceEmbeddings(
                    model_name=model_path,
                    model_kwargs={"device": "cpu"},
                    encode_kwargs={"normalize_embeddings": True},
                )
                # 测试加载是否正常
                _ = embeddings.embed_query("测试")
                _embedding_instance = embeddings
                _embedding_source = f"local:{model_path}"
                logger.info(f"Embedding 已加载（本地模型）: {model_path}")
                return embeddings

            except Exception as e:
                logger.warning(f"本地 Embedding 模型加载失败: {e}，回退到智谱AI API")

    # ===== 方案 2: 智谱AI API 回退 =====
    if zhipuai_api_key:
        try:
            from langchain_community.embeddings import ZhipuAIEmbeddings

            embeddings = ZhipuAIEmbeddings(
                model=zhipuai_model,
                api_key=zhipuai_api_key,
            )
            _embedding_instance = embeddings
            _embedding_source = f"api:zhipuai/{zhipuai_model}"
            logger.info(f"Embedding 已加载（智谱AI API）: {zhipuai_model}")
            return embeddings

        except Exception as e:
            logger.error(f"智谱AI Embedding 初始化也失败: {e}")
            raise RuntimeError(
                "无法初始化任何 Embedding 模型。"
                f"本地模型路径 {model_path} 加载失败，智谱AI API 也不可用。"
            )

    raise RuntimeError(
        f"无法初始化 Embedding：本地模型路径 {model_path} 不可用，"
        "且未提供 ZHIPUAI_API_KEY"
    )


def get_embedding_source() -> str:
    """获取当前 Embedding 来源（用于调试和监控）"""
    return _embedding_source


def clear_embedding_cache():
    """清除 Embedding 实例缓存（用于重新加载）"""
    global _embedding_instance, _embedding_source
    _embedding_instance = None
    _embedding_source = "unknown"
