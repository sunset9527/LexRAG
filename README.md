# LexRAG — 法律知识增强检索系统

基于结构化 RAG + ReAct Agent + 法条自校验的垂直领域法律问答系统。v1.8 已升级为 Vue 3 前端 + 本地 BGE-M3 Embedding。

## 项目介绍

  通用 RAG 在法律场景下存在"幻觉法条"的严重问题——模型可能编造不存在的法条编号或内容。LexRAG 通过以下三个核心设计解决这一问题：

1. **法律原生文档解析**：按"编→章→节→条→款→项"六级层级切分，而非通用按字符数 chunking
2. **混合检索管线**：语义检索 + BM25 关键词检索（BGE-M3 本地 Embedding），兼顾语义理解和编号精确匹配
3. **法条自校验**：回答生成后自动提取引用的法条编号，检索原文逐条比对，不一致则触发修正
4. **本地 Embedding**：BGE-M3 本地加载（1024 维），无需外部 Embedding API
5. **Vue 3 产品化前端**：Dashboard / 法律咨询（双栏+法条溯源）/ 法律检索 / 知识图谱（ECharts）/ 法规浏览 / 多模型切换

系统以中国《民法典》为示例数据，架构设计适用于任何有层级结构的法律文本。

## 系统架构

```
用户法律咨询 (Vue 3)
    │  X-API-Key / X-Model header
    ▼
FastAPI Gateway
    │
    ├── app/api/auth.py        # JWT 登录/注册
    ├── app/api/prompts.py     # Prompt CRUD + 热加载
    ├── app/models/            # SQLAlchemy (User/ChatHistory/Prompt)
    ├── app/services/          # 业务逻辑 + Langfuse 可观测
    └── app/db/               # MySQL + Alembic 迁移
    │
    ▼
LangGraph ReAct Agent
    ├── 查询改写 (QueryRewriter)
    ├── 意图路由 (IntentRouter: 6 类意图)
    ├── 混合检索
    │   ├── ChromaDB 语义检索 (BGE-M3 本地 1024维)
    │   ├── BM25 关键词检索 (jieba)
    │   └── RRF 结果融合
    ├── 知识图谱 (NetworkX 有向图 + BFS)
    └── 上下文压缩 (ContextCompressor)
    │
    ▼
答案生成 + 法条引用标注
    │
    ▼
自校验 Agent (提取引用 → 检索原文 → 比对)
    ├── PASS → 输出
    └── FAIL → 修正重试 (最多2轮)
```

## 功能介绍

### 核心功能

| 功能 | 说明 |
|------|------|
| **法律问答** | 支持法条查询、案例匹配、法律适用分析等意图 |
| **结构化检索** | 按法律层级精确检索，保留编/章/节上下文 |
| **多跳推理** | 复杂问题链式引用多个法条，BFS 遍历引用图 |
| **法条自校验** | 回答与法条原文逐一比对，校验失败自动修正（最多2轮） |
| **知识图谱** | 法条间引用关系建模，ECharts 力导向图可视化 |
| **本地 Embedding** | BGE-M3 本地加载，1024 维，无需外部 API |
| **JWT 认证** | 登录/注册 + Token 刷新，localStorage 持久化 |
| **多模型切换** | 6 个 LLM 提供商，前端 Settings 页一键切换 |
| **Prompt 管理** | 数据库存储 + CRUD API + 版本递增 + 热加载 |
| **Langfuse 可观测** | Token/延迟/成本追踪（可选启用） |
| **文档上传** | 支持上传法律文档自动解析、切分、建索引 |

### 六大技术深度

| 深度点 | 问题 | 方案 |
|--------|------|------|
| 结构化切分 | 按字符数切分破坏法条完整性 | 自研 LawParser，按六级层级切分 |
| 混合检索 | 向量检索对法条编号不敏感 | ChromaDB + BM25 双路 + RRF 融合（BGE-M3 本地 1024 维） |
| 意图路由 | 不同法律问题需要不同检索策略 | LLM 驱动的 6 类意图分类 |
| 多跳推理 | 单次检索无法覆盖跨法条问题 | LangGraph ReAct + BFS 图谱遍历 |
| 自校验 | 模型可能编造法条 | 独立校验 Agent，提取引用→检索原文→比对 |
| 版本管理 | 法条有修订历史 | VersionManager + 生效日期过滤 |

[//]: # (## 演示)

[//]: # ()
[//]: # (<table>)

[//]: # (<tr>)

[//]: # (<td align="center"><b>法律问答</b><br><img src="docs/gifs/query.gif" width="400"/><br><i>输入法律问题，Agent自主选择工具检索并回答</i></td>)

[//]: # (<td align="center"><b>法条溯源</b><br><img src="docs/gifs/citation.gif" width="400"/><br><i>每条回答标注法条出处，点击查看原文</i></td>)

[//]: # (</tr>)

[//]: # (<tr>)

[//]: # (<td align="center"><b>文档上传</b><br><img src="docs/gifs/upload.gif" width="400"/><br><i>上传法律文档，自动解析切分建索引</i></td>)

[//]: # (<td align="center"><b>知识图谱</b><br><img src="docs/gifs/graph.gif" width="400"/><br><i>法条引用关系图谱，支持多跳检索</i></td>)

[//]: # (</tr>)

[//]: # (</table>)


## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| LLM | DeepSeek / 千问 / GLM / OpenAI / Claude / 自定义 | 对话生成、意图识别、自校验（前端 Settings 切换） |
| Agent 编排 | LangGraph | ReAct Agent 工作流，4 工具自主调用 |
| 检索框架 | LangChain | 文档加载、检索链抽象 |
| 向量数据库 | ChromaDB | 法条向量存储与语义检索 |
| 本地 Embedding | BAAI/bge-m3 | 本地加载，1024 维，支持 dense+sparse 混合检索 |
| 关键词检索 | BM25 + jieba | 法条编号精确匹配 |
| 知识图谱 | NetworkX | 法条引用关系建模，BFS 多跳检索 |
| 关系型数据库 | MySQL + SQLAlchemy + Alembic | 用户/ChatHistory/Prompt 持久化 |
| 认证 | JWT (python-jose + bcrypt) | OAuth2PasswordBearer 登录/注册 |
| LLM 可观测 | Langfuse | Token/延迟/成本追踪（可选） |
| 后端 | FastAPI | RESTful API，Lifespan 资源管理 |
| 前端 | Vue 3 + Vite + TypeScript | 7 页面 SPA（Element Plus + Tailwind CSS + ECharts） |
| 反向代理 | Nginx | HTTPS + gzip + API 代理 |
| 配置 | Pydantic Settings | 集中配置管理，.env 环境变量 |
| 测试 | pytest | 核心模块单元测试 |
| CI/CD | GitHub Actions | ruff lint + pytest (Python 3.11/3.12) |
| 部署 | Docker Compose | API + Vue + MySQL + Redis + Nginx 一键部署 |

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+（前端）
- （可选）DeepSeek API Key — 在前端 Settings 页面填入，.env 不需配置

### 本地运行

```bash
# 1. 克隆项目
git clone https://github.com/sunset9527/LexRAG.git
cd LexRAG

# 2. 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 4. （可选）配置 .env — 留空即可，API Key 在前端页面填入
cp .env.example .env

# 5. 初始化知识库（构建向量索引和图谱）
python init.py

# 6. 启动服务
# 终端1：启动 API
uvicorn api:app --host 0.0.0.0 --port 8000

# 终端2：启动前端
cd frontend && npm run dev
```

访问：
- 前端界面：http://localhost:3000（首次使用请进入 Settings 填入 API Key）
- API 文档：http://localhost:8000/docs

> ⚠️ 国内用户：已默认配置 HuggingFace 镜像 `hf-mirror.com`，Embedding 模型 `BGE-M3` 从本地 `E:\huggingface\model` 加载。如需使用远程 Embedding API，请在 `.env` 中配置 `ZHIPUAI_API_KEY`。

## Docker 部署

```bash
# 1. （可选）配置 .env
cp .env.example .env

# 2. 一键启动（API + Vue + MySQL + Redis + Nginx）
docker compose up -d

# 3. 初始化知识库（首次运行）
docker compose exec api python init.py
```

访问：
- Web 界面：http://localhost:3000
- API 文档：http://localhost:8000/docs

```bash
# 查看日志
docker compose logs -f

# 停止
docker compose down
```

## API 文档

### 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 根路径，返回系统信息 |
| GET | `/health` | 健康检查（含组件状态 + Embedding 来源） |
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 用户登录（返回 JWT Token） |
| GET | `/auth/me` | 获取当前用户信息 |
| POST | `/query` | 法律问答（支持 X-API-Key / X-Base-URL / X-Model header） |
| POST | `/upload` | 上传法律文档 |
| GET | `/graph` | 获取知识图谱数据（含 ECharts 可视化数据） |
| POST | `/graph/query` | 图谱查询（多跳检索） |
| GET | `/prompts` | Prompt 模板列表 |
| POST | `/prompts` | 创建 Prompt 模板 |

### `/query` — 法律问答

请求：
```json
{
  "query": "合同成立需要满足哪些条件？",
  "session_id": "optional-session-id",
  "config": {}
}
```

支持通过 HTTP Header 传入用户配置：
| Header | 说明 |
|--------|------|
| `X-API-Key` | 用户自己的 LLM API Key（从前端 Settings 传入） |
| `X-Base-URL` | 用户选择的 API Base URL |
| `X-Model` | 用户选择的模型名称 |

响应：
```json
{
  "query_id": "uuid",
  "query": "合同成立需要满足哪些条件？",
  "answer": "根据《民法典》...",
  "intent": "legal_application",
  "citations": [
    {
      "article_id": "民法典第464条",
      "citation_text": "...",
      "original_text": "...",
      "is_verified": true
    }
  ],
  "verification_status": "pass",
  "verification_issues": [],
  "sub_questions": [],
  "metadata": {
    "query_id": "uuid",
    "created_at": "...",
    "verification_attempts": 0
  }
}
```

### `/upload` — 上传法律文档

请求：`multipart/form-data`
| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | file | 法律文档（.txt） |
| `law_name` | string | 法律名称 |

### `/health` — 健康检查

响应：
```json
{
  "status": "healthy",
  "timestamp": "2026-07-27T...",
  "version": "1.7.0",
  "components": {
    "workflow": "ready",
    "law_indexer": "ready",
    "law_graph": "ready"
  }
}
```

## 项目目录

```
LexRAG/
├── README.md                        # 项目文档
├── requirements.txt                 # Python 依赖
├── pyproject.toml                   # Python 项目配置（ruff/pytest）
├── config.py                        # Pydantic Settings 配置
├── api.py                           # FastAPI 后端（v1.7: 认证/Prompt/Langfuse）
├── init.py                          # 知识库初始化脚本
├── alembic.ini                      # Alembic 数据库迁移配置
├── Dockerfile                       # Docker 多阶段构建
├── docker-compose.yml               # Docker Compose（API+Vue+MySQL+Redis+Nginx）
├── .dockerignore
├── .env.example                     # 环境变量模板
├── .github/workflows/               # GitHub Actions CI/CD
│   └── ci.yml                       #   ruff lint + pytest
├── alembic/                         # 数据库迁移
├── app/                             # v1.7: 应用层
│   ├── api/                         #   认证 & Prompt 路由
│   │   ├── auth.py                  #     /auth/register /auth/login /auth/me
│   │   └── prompts.py               #     Prompt CRUD + 热加载
│   ├── db/                          #   数据库会话 & Base
│   ├── models/                      #   SQLAlchemy 模型
│   │   ├── user.py                  #     User 表
│   │   ├── chat_history.py          #     ChatHistory 表
│   │   └── prompt.py                #     Prompt 表（版本递增）
│   └── services/                    #   业务逻辑
│       ├── auth_service.py          #     JWT + bcrypt
│       ├── prompt_service.py        #     Prompt 管理
│       └── langfuse_helper.py       #     create_llm() 可观测工厂
├── frontend/                        # v1.8: Vue 3 前端
│   ├── src/
│   │   ├── views/                   #   7 页面
│   │   │   ├── Dashboard.vue        #     数据仪表盘
│   │   │   ├── Chat.vue             #     法律咨询（双栏+法条溯源）
│   │   │   ├── Search.vue           #     法律检索
│   │   │   ├── Graph.vue            #     知识图谱（ECharts）
│   │   │   ├── Laws.vue             #     法规浏览（树形目录）
│   │   │   ├── Settings.vue         #     模型/API Key 管理
│   │   │   ├── Login.vue            #     登录
│   │   │   └── Register.vue         #     注册
│   │   ├── api/                     #   Axios 封装 + API 层
│   │   ├── stores/                  #   Pinia 状态管理
│   │   │   ├── auth.ts              #     认证状态
│   │   │   ├── chat.ts              #     对话状态
│   │   │   └── settings.ts          #     设置状态（6 提供商）
│   │   └── router/                  #   Vue Router
│   ├── nginx.conf                   #   Nginx 反向代理
│   └── Dockerfile                   #   前端 Docker 镜像
├── src/
│   ├── agent/                       # Agent 模块
│   │   ├── workflow.py              #   LangGraph ReAct 主工作流
│   │   ├── nodes.py                 #   工作流节点
│   │   ├── tools.py                 #   4 个 Agent 工具定义
│   │   └── state.py                 #   状态定义与数据结构
│   ├── ingestion/                   # 文档解析
│   │   ├── law_parser.py            #   六级层级解析
│   │   ├── chunker.py               #   按法律层级切分
│   │   └── indexer.py               #   ChromaDB 索引（Embedding 工厂）
│   ├── retrieval/                   # 检索模块
│   │   ├── intent_router.py         #   6 类意图路由
│   │   ├── law_retriever.py         #   法条语义检索
│   │   ├── case_retriever.py        #   案例检索
│   │   ├── graph_retriever.py       #   图谱多跳检索
│   │   ├── bm25_retriever.py        #   BM25 关键词检索
│   │   ├── query_rewriter.py        #   口语→术语查询改写
│   │   ├── reranker.py              #   CrossEncoder 重排序（v1.8已禁用）
│   │   ├── fusion.py                #   RRF 混合检索融合
│   │   └── context_compressor.py    #   上下文压缩
│   ├── reasoning/                   # 推理模块
│   │   ├── multi_hop.py             #   多跳法律推理
│   │   └── self_verify.py           #   法条引用自校验
│   ├── graph/                       # 图谱模块
│   │   ├── law_graph.py             #   NetworkX 有向图
│   │   └── builder.py               #   图谱构建
│   └── utils/                       # 工具模块
│       ├── embedding_factory.py     #   Embedding 工厂（本地 BGE-M3 优先）
│       └── version_manager.py       #   法条版本管理
├── data/
│   ├── laws/                        # 法律文档
│   ├── cases/                       # 案例
│   ├── law_graph.json               # 知识图谱（运行时生成）
│   └── chroma_db/                   # 向量数据库（运行时生成）
└── tests/                           # 测试
    ├── test_structured_chunking.py
    ├── test_intent_router.py
    ├── test_multi_hop.py
    └── test_self_verify.py
```

## Release

### v1.8.0 (2026-07-27) — 前端现代化

- ✨ Vue 3 + Vite + TypeScript 全栈重构（7 页面 SPA）
- ✨ 双栏法律咨询：对话区 + 法条溯源面板（自动列出引用）
- ✨ ECharts 力导向知识图谱可视化
- ✨ 6 个 LLM 提供商切换（DeepSeek/千问/GLM/OpenAI/Claude/自定义）
- ✨ Nginx 反向代理 + Docker Compose 全栈编排
- ✨ 本地 BGE-M3 Embedding（1024 维，无需外部 API）
- ✨ API Key 前端 Settings 注入（.env 不再需要配置 Key）
- 🔧 HuggingFace 国内镜像（hf-mirror.com）
- 🔧 Reranker 暂禁（国内镜像不兼容，BGE-M3 混合检索替代）
- 🗑️ 删除 Streamlit 前端，删除 Agent 推理面板

### v1.7.0 (2026-07-11) — 产品地基

- ✨ JWT 认证系统（OAuth2PasswordBearer + bcrypt）
- ✨ MySQL + SQLAlchemy + Alembic 数据库迁移
- ✨ Prompt 管理（DB 存储 + CRUD API + 版本递增 + 热加载）
- ✨ Langfuse LLM 可观测性（create_llm 工厂统一注入）
- ✨ GitHub Actions CI/CD（ruff lint + pytest）
- ✨ ChatHistory 表 + 会话持久化

### v1.6.0 (2026-06-29)

- ✨ Docker Compose 一键部署支持
- 📝 技术博客：法律 RAG 自校验设计实践
- 📖 README 重构：架构图 / API 文档 / 项目目录

### v1.5.0 (2026-06-05)

- ✨ 法条自校验模块（提取引用 → 检索原文 → 比对判定）
- ✨ 校验失败自动修正（最多 2 轮）
- ✅ 核心模块 pytest 测试覆盖

### v1.4.0 (2026-05-22)

- ✨ LangGraph ReAct Agent 主工作流
- ✨ 4 工具：search_statute / search_case / lookup_article / analyze_legal_relation
- 🐛 Agent 重复调用工具问题修复

### v1.3.0 (2026-05-08)

- ✨ 法律知识图谱（NetworkX 有向图）
- ✨ 图谱多跳 BFS 检索（默认 3 跳）
- ✨ 上下文压缩器（ContextCompressor）

### v1.2.0 (2026-04-22)

- ✨ 法条引用自校验 SelfVerifier
- ✨ 多跳法律推理引擎
- ✨ 查询改写 + 案例检索

### v1.1.0 (2026-04-01)

- ✨ 意图路由器 IntentRouter（4 类意图）
- ✨ CrossEncoder Reranker 重排序
- ✨ BM25 + 向量混合检索结果融合

### v1.0.0 (2026-03-15)

- 🎉 首次发布
- ✨ 法律文档结构化解析器 LawParser
- ✨ ChromaDB 向量索引
- ✨ 基础问答 + FastAPI + Streamlit

