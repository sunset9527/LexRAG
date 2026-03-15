"""
法律RAG智能体知识增强系统 - 配置文件

集中管理所有配置项，支持环境变量覆盖
"""

from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """应用配置类"""
    
    # API配置
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    
    # 智谱AI Embedding配置
    zhipuai_api_key: Optional[str] = None
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 1024

    # 向量数据库配置
    chroma_persist_directory: str = "./data/chroma_db"
    
    # 检索配置
    retrieval_top_k: int = 5
    graph_max_hops: int = 3
    verification_max_retries: int = 2
    
    # BM25配置
    bm25_enabled: bool = True
    
    # Reranker配置
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = True
    
    # 查询增强配置
    query_rewriting_enabled: bool = True
    hyde_enabled: bool = False
    
    # RRF融合配置
    rrf_k: int = 60
    
    # 上下文压缩配置
    context_max_tokens: int = 4000
    context_compress_enabled: bool = True
    
    # 知识图谱配置
    law_graph_path: str = "./data/law_graph.json"
    
    # 数据路径配置
    laws_data_path: str = "./data/laws"
    cases_data_path: str = "./data/cases"
    
    # FastAPI配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Streamlit配置
    streamlit_port: int = 8501
    
    # 日志配置
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 向量库集合名称
    law_collection_name: str = "law_articles"
    case_collection_name: str = "legal_cases"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent


def ensure_directories():
    """确保必要目录存在"""
    dirs = [
        settings.chroma_persist_directory,
        settings.laws_data_path,
        settings.cases_data_path,
    ]
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)


# 初始化时创建目录
ensure_directories()
