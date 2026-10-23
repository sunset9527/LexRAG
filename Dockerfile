# Docker 部署 — LexRAG 法律知识增强检索系统
# 多阶段构建：API 服务

FROM python:3.13-slim AS base

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

COPY requirements.txt constraints-py313.txt ./
RUN pip install --no-cache-dir -c constraints-py313.txt -r requirements.txt

# ==================== API 服务 ====================
FROM dependencies AS api

COPY config.py .
COPY app/ ./app/
COPY src/ ./src/
COPY api.py .
COPY init.py .
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY data/ ./data/
COPY scripts/bootstrap_runtime.py ./scripts/bootstrap_runtime.py
COPY scripts/check_worker_health.py ./scripts/check_worker_health.py

RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
