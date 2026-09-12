"""
法律RAG智能体知识增强系统 - 配置文件

集中管理所有配置项，支持环境变量覆盖
"""

from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """应用配置类"""

    # ==================== API 配置 ====================
    deepseek_api_key: Optional[str] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    # ==================== Embedding 配置 ====================
    # 本地模型路径（优先使用，如 E:/huggingface/model 下的 BGE-M3）
    local_embedding_model_path: str = "E:/huggingface/model"
    # 智谱AI（本地模型不可用时回退）
    zhipuai_api_key: Optional[str] = None
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 1024
    # HuggingFace 镜像（国内加速）
    hf_endpoint: str = "https://hf-mirror.com"

    # ==================== 数据库配置 ====================
    database_url: Optional[str] = None
    """数据库连接 URL。不设置则默认使用 MySQL。
    示例（MySQL）：mysql+pymysql://root:123456@localhost:3306/lexrag
    示例（PostgreSQL）：postgresql://user:pass@localhost:5432/lexrag
    """
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "lexrag"
    """MySQL 连接参数（database_url 为空时使用）"""
    db_echo: bool = False
    """是否打印 SQL 语句（调试用）"""

    # ==================== JWT 认证配置 ====================
    jwt_secret_key: str = "lexrag-dev-secret-change-in-production"
    """JWT 签名密钥。生产环境必须通过环境变量覆盖！"""
    jwt_access_token_expire_minutes: int = 1440
    """JWT 令牌过期时间（分钟），默认 24 小时"""

    # ==================== Langfuse 可观测性配置 ====================
    langfuse_enabled: bool = True
    """是否启用 Langfuse 可观测性"""
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"
    """Langfuse 服务地址（自部署时修改）"""
    langfuse_release: str = "v1.7.0"
    """当前发布版本标识"""

    # ==================== 向量数据库配置 ====================
    chroma_persist_directory: str = "./data/chroma_db"

    # ==================== 检索配置 ====================
    retrieval_top_k: int = 5
    graph_max_hops: int = 3
    verification_max_retries: int = 2

    # BM25 配置
    bm25_enabled: bool = True

    # Reranker 配置
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = False  # 禁用：hf-mirror 不支持该模型，本地 BGE-M3 已足够

    # 查询增强配置
    query_rewriting_enabled: bool = True
    hyde_enabled: bool = False

    # RRF 融合配置
    rrf_k: int = 60

    # 上下文压缩配置
    context_max_tokens: int = 4000
    context_compress_enabled: bool = True

    # ==================== 知识图谱配置 ====================
    law_graph_path: str = "./data/law_graph.json"

    # ==================== 数据路径配置 ====================
    laws_data_path: str = "./data/laws"
    cases_data_path: str = "./data/cases"
    document_uploads_path: str = "./data/uploads"

    # ==================== 异步文档任务配置 ====================
    redis_url: str = "redis://localhost:6379/0"
    document_uploads_path: str = "./data/uploads"

    # ==================== 异步文档任务配置 ====================
    redis_url: str = "redis://localhost:6379/0"

    # ==================== FastAPI 配置 ====================
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ==================== Streamlit 配置 ====================
    streamlit_port: int = 8501

    # ==================== 日志配置 ====================
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ==================== 向量库集合名称 ====================
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
        settings.document_uploads_path,
        settings.document_uploads_path,
    ]
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)


# 初始化时创建目录
ensure_directories()
