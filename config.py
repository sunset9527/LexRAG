"""
法律RAG智能体知识增强系统 - 配置文件

集中管理所有配置项，支持环境变量覆盖
"""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings

DEVELOPMENT_JWT_SECRET = "lexrag-dev-secret-change-in-production"
DEMONSTRATION_DATABASE_PASSWORD = "123456"


class SecurityConfigurationError(RuntimeError):
    """The application security configuration is unsafe or internally inconsistent."""


class Settings(BaseSettings):
    """应用配置类"""

    # ==================== 运行模式与安全边界 ====================
    app_mode: Literal["development", "demo", "production"] = "development"
    open_registration: bool = True
    auth_cookie_name: str = "lexrag_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict"] = "lax"

    # ==================== API 配置 ====================
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"

    # ==================== Embedding 配置 ====================
    # provider 必须显式选择；任一 provider 失败都不允许切换到另一个 provider。
    embedding_provider: Literal["local", "zhipu"] = "local"
    # 容器内固定的只读本地 BGE-M3 挂载路径。
    local_embedding_model_path: str = "/models/bge-m3"
    # 本地路径不进入 fingerprint，稳定模型标识才进入。
    local_embedding_model_id: str = "BAAI/bge-m3"
    # 智谱 Embedding 只在 embedding_provider=zhipu 时使用。
    zhipuai_api_key: str | None = None
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 1024
    embedding_normalize: bool = True
    index_schema_version: int = 1
    # HuggingFace 镜像（国内加速）
    hf_endpoint: str = "https://hf-mirror.com"

    # ==================== 数据库配置 ====================
    database_url: str | None = None
    """数据库连接 URL。不设置则默认使用 MySQL。
    示例（MySQL）：mysql+pymysql://root:123456@localhost:3306/lexrag
    示例（PostgreSQL）：postgresql://user:pass@localhost:5432/lexrag
    """
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = DEMONSTRATION_DATABASE_PASSWORD
    mysql_database: str = "lexrag"
    """MySQL 连接参数（database_url 为空时使用）"""
    db_echo: bool = False
    """是否打印 SQL 语句（调试用）"""

    # ==================== JWT 认证配置 ====================
    jwt_secret_key: str = DEVELOPMENT_JWT_SECRET
    """JWT 签名密钥。生产环境必须通过环境变量覆盖！"""
    jwt_access_token_expire_minutes: int = 1440
    """JWT 令牌过期时间（分钟），默认 24 小时"""

    # ==================== Langfuse 可观测性配置 ====================
    langfuse_enabled: bool = False
    """是否启用 Langfuse 可观测性"""
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
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

    # ==================== Stage 2 资源保护 ====================
    upload_max_bytes: int = 20 * 1024 * 1024
    upload_batch_max_bytes: int = 50 * 1024 * 1024
    upload_batch_max_files: int = 10
    upload_max_pdf_pages: int = 500
    upload_max_extracted_characters: int = 2_000_000
    upload_docx_max_entries: int = 10_000
    upload_docx_max_uncompressed_bytes: int = 100 * 1024 * 1024
    upload_docx_max_entry_bytes: int = 20 * 1024 * 1024
    document_task_soft_time_limit_seconds: int = 15 * 60
    document_task_time_limit_seconds: int = 16 * 60
    runtime_llm_timeout_seconds: int = 90
    runtime_llm_max_output_tokens: int = 4096
    runtime_llm_max_retries: int = 2
    runtime_llm_max_concurrency: int = 8
    runtime_llm_trusted_base_urls: str = (
        "https://api.deepseek.com,"
        "https://dashscope.aliyuncs.com/compatible-mode/v1,"
        "https://open.bigmodel.cn/api/paas/v4,"
        "https://api.openai.com/v1,"
        "https://api.anthropic.com"
    )
    rate_limit_window_seconds: int = 60
    rate_limit_auth: int = 10
    rate_limit_query: int = 60
    rate_limit_upload: int = 20
    rate_limit_retry: int = 10
    rate_limit_admin_write: int = 30

    # ==================== v2.0 查询缓存配置 ====================
    query_cache_ttl_seconds: int = 3600
    query_cache_semantic_threshold: float = 0.9
    query_cache_retrieval_version: str = "v2.0"

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


def validate_security_settings(candidate: Settings) -> None:
    """Fail closed when resource limits or production secrets are unsafe.

    Error messages name configuration keys but deliberately never echo values.
    """

    invalid: list[str] = []
    if not 0 < candidate.upload_max_bytes <= 50 * 1024 * 1024:
        invalid.append("upload_max_bytes")
    if not candidate.upload_max_bytes <= candidate.upload_batch_max_bytes <= 250 * 1024 * 1024:
        invalid.append("upload_batch_max_bytes")
    if not 1 <= candidate.upload_batch_max_files <= 50:
        invalid.append("upload_batch_max_files")
    if not 0 < candidate.upload_max_pdf_pages <= 2_000:
        invalid.append("upload_max_pdf_pages")
    if not 0 < candidate.upload_max_extracted_characters <= 10_000_000:
        invalid.append("upload_max_extracted_characters")
    if not (
        0 < candidate.document_task_soft_time_limit_seconds
        < candidate.document_task_time_limit_seconds
        <= 3600
    ):
        invalid.append("document_task_time_limit_seconds")
    if not 0 < candidate.runtime_llm_timeout_seconds <= 120:
        invalid.append("runtime_llm_timeout_seconds")
    if not 0 < candidate.runtime_llm_max_output_tokens <= 16_384:
        invalid.append("runtime_llm_max_output_tokens")
    if not 0 <= candidate.runtime_llm_max_retries <= 3:
        invalid.append("runtime_llm_max_retries")
    if not 0 < candidate.runtime_llm_max_concurrency <= 32:
        invalid.append("runtime_llm_max_concurrency")
    if not 1 <= candidate.rate_limit_window_seconds <= 3600:
        invalid.append("rate_limit_window_seconds")
    for name in (
        "rate_limit_auth",
        "rate_limit_query",
        "rate_limit_upload",
        "rate_limit_retry",
        "rate_limit_admin_write",
    ):
        if not 1 <= getattr(candidate, name) <= 10_000:
            invalid.append(name)

    if candidate.app_mode == "production":
        if candidate.jwt_secret_key == DEVELOPMENT_JWT_SECRET or len(candidate.jwt_secret_key) < 32:
            invalid.append("jwt_secret_key")
        if candidate.database_url:
            database_password = urlsplit(candidate.database_url).password
            if database_password in {None, "", DEMONSTRATION_DATABASE_PASSWORD}:
                invalid.append("database_url")
        elif candidate.mysql_password == DEMONSTRATION_DATABASE_PASSWORD:
            invalid.append("mysql_password")
        if candidate.open_registration:
            invalid.append("open_registration")
        if not candidate.auth_cookie_secure:
            invalid.append("auth_cookie_secure")
        if not candidate.runtime_llm_trusted_base_urls.strip():
            invalid.append("runtime_llm_trusted_base_urls")

    if invalid:
        names = ", ".join(dict.fromkeys(invalid))
        raise SecurityConfigurationError(f"Unsafe security configuration: {names}")


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
