# Docker 部署 — LexRAG 法律知识增强检索系统
# 多阶段构建：API 服务 + Streamlit 前端

FROM python:3.11-slim AS base

LABEL maintainer="zygao2018@163.com"
LABEL project="LexRAG"
LABEL description="法律RAG智能体 — 结构化检索+多跳推理+法条自校验"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

# 使用国内 PyPI 镜像加速（阿里云）
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==================== API 服务 ====================
FROM dependencies AS api

COPY config.py .
COPY app/ ./app/
COPY src/ ./src/
COPY api.py .
COPY init.py .
COPY data/ ./data/

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

# ==================== Streamlit 前端 ====================
FROM dependencies AS frontend

COPY config.py .
COPY src/ ./src/
COPY main.py .
COPY api.py .
COPY data/ ./data/

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
