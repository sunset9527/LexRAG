# LexRAG — 法律知识增强检索系统

基于结构化 RAG + ReAct Agent + 法条自校验的垂直领域法律问答系统。

## 项目介绍

通用 RAG 在法律场景下存在"幻觉法条"的严重问题——模型可能编造不存在的法条编号或内容。LexRAG 通过以下三个核心设计解决这一问题：

1. **法律原生文档解析**：按"编→章→节→条→款→项"六级层级切分，而非通用按字符数 chunking
2. **混合检索管线**：语义检索 + BM25 关键词检索 + CrossEncoder 重排序，兼顾语义理解和编号精确匹配
3. **法条自校验**：回答生成后自动提取引用的法条编号，检索原文逐条比对，不一致则触发修正

系统以中国《民法典》为示例数据，架构设计适用于任何有层级结构的法律文本。

## 系统架构

```
用户法律咨询
    │
    ▼
┌──────────────┐     ┌──────────────────┐
│  查询改写     │────▶│  意图路由器       │
│  (口语→术语)  │     │  (法条/案例/适用)  │
└──────────────┘     └──────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ 法条检索  │ │ 案例检索  │ │ 图谱检索  │
        │ (ChromaDB)│ │ (语义匹配)│ │ (NetworkX)│
        └─────┬────┘ └─────┬────┘ └─────┬────┘
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                   ┌────────────────┐
                   │  混合检索融合   │
                   │ (BM25+向量+Rerank)│
                   └───────┬────────┘
                           ▼
                   ┌────────────────┐
                   │  ReAct Agent   │
                   │  (4工具自主决策) │
                   └───────┬────────┘
                           ▼
                   ┌────────────────┐
                   │  答案生成       │
                   │  + 法条引用标注  │
                   └───────┬────────┘
                           ▼
                   ┌────────────────┐
                   │  自校验 Agent   │
                   │  (提取引用→比对) │
                   ├────────────────┤
                   │ PASS → 输出     │
                   │ FAIL → 修正重试  │
                   └────────────────┘
```

## 功能介绍

### 核心功能

| 功能 | 说明 |
|------|------|
| **法律问答** | 支持法条查询、案例匹配、法律适用分析等意图 |
| **结构化检索** | 按法律层级精确检索，保留编/章/节上下文 |
| **多跳推理** | 复杂问题链式引用多个法条，BFS 遍历引用图 |
| **法条自校验** | 回答与法条原文逐一比对，校验失败自动修正（最多2轮） |
| **知识图谱** | 法条间引用关系建模，支持多跳图谱检索 |
| **文档上传** | 支持上传法律文档自动解析、切分、建索引 |

### 六大技术深度

| 深度点 | 问题 | 方案 |
|--------|------|------|
| 结构化切分 | 按字符数切分破坏法条完整性 | 自研 LawParser，按六级层级切分 |
| 混合检索 | 向量检索对法条编号不敏感 | ChromaDB + BM25 + CrossEncoder 三阶段 |
| 意图路由 | 不同法律问题需要不同检索策略 | LLM 驱动的 4 类意图分类 |
| 多跳推理 | 单次检索无法覆盖跨法条问题 | LangGraph ReAct + BFS 图谱遍历 |
| 自校验 | 模型可能编造法条 | 独立校验 Agent，提取引用→检索原文→比对 |
| 版本管理 | 法条有修订历史 | VersionManager + 生效日期过滤 |

## 演示

> 以下为系统实际运行效果截图，点击查看完整交互流程。

<table>
<tr>
<td align="center"><b>法律问答</b><br><img src="docs/gifs/query.gif" width="400"/><br><i>输入法律问题，Agent自主选择工具检索并回答</i></td>
<td align="center"><b>法条溯源</b><br><img src="docs/gifs/citation.gif" width="400"/><br><i>每条回答标注法条出处，点击查看原文</i></td>
</tr>
<tr>
<td align="center"><b>文档上传</b><br><img src="docs/gifs/upload.gif" width="400"/><br><i>上传法律文档，自动解析切分建索引</i></td>
<td align="center"><b>知识图谱</b><br><img src="docs/gifs/graph.gif" width="400"/><br><i>法条引用关系图谱，支持多跳检索</i></td>
</tr>
</table>

> 💡 如需录制演示 GIF，推荐使用 [ScreenToGif](https://www.screentogif.com/)（Windows 免费开源），录制后放入 `docs/gifs/` 目录。

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| LLM | DeepSeek API | 对话生成、意图识别、自校验 |
| Agent 编排 | LangGraph | ReAct Agent 工作流，4 工具自主调用 |
| 检索框架 | LangChain | 文档加载、检索链抽象 |
| 向量数据库 | ChromaDB | 法条向量存储与语义检索 |
| 关键词检索 | BM25 + jieba | 法条编号精确匹配 |
| 重排序 | BAAI/bge-reranker-v2-m3 | 检索结果精排 |
| 知识图谱 | NetworkX | 法条引用关系建模，BFS 多跳检索 |
| 后端 | FastAPI | RESTful API，Lifespan 资源管理 |
| 前端 | Streamlit | 三栏布局 Web 界面 |
| 配置 | Pydantic Settings | 集中配置管理，.env 环境变量 |
| 测试 | pytest | 核心模块单元测试 |

## 快速开始

### 前置条件

- Python 3.11+
- DeepSeek API Key（[注册获取](https://platform.deepseek.com/)）

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

# 4. 配置 API Key
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY=sk-xxx

# 5. 初始化知识库（构建向量索引和图谱）
python init.py

# 6. 启动服务
# 终端1：启动 API
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 终端2：启动前端
streamlit run main.py
```

访问 http://localhost:8501 进入 Web 界面，http://localhost:8000/docs 查看 API 文档。

## Docker 部署

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY=sk-xxx

# 2. 一键启动（API + 前端）
docker compose up -d

# 3. 初始化知识库（首次运行）
docker compose exec api python init.py
```

访问：
- Web 界面：http://localhost:8501
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
| GET | `/health` | 健康检查（含组件状态） |
| POST | `/query` | 法律问答 |
| POST | `/upload` | 上传法律文档 |
| GET | `/graph` | 获取知识图谱数据 |
| POST | `/graph/query` | 图谱查询（多跳检索） |
| GET | `/verify/{query_id}` | 查询指定回答的校验结果 |

### `/query` — 法律问答

请求：
```json
{
  "question": "合同成立需要满足哪些条件？",
  "enable_rewriting": true,
  "max_verification_retries": 2
}
```

响应：
```json
{
  "query_id": "uuid",
  "question": "合同成立需要满足哪些条件？",
  "answer": "根据《民法典》...",
  "intent": "statute_lookup",
  "citations": [
    {
      "article_id": "民法典第143条",
      "citation_text": "具备下列条件的民事法律行为有效...",
      "original_text": "...",
      "is_verified": true
    }
  ],
  "verification_status": "pass",
  "reasoning_trace": [...]
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
├── README.md                     # 项目文档
├── requirements.txt              # Python 依赖
├── config.py                     # Pydantic Settings 配置
├── api.py                        # FastAPI 后端 (7 端点)
├── main.py                       # Streamlit 前端 (三栏布局)
├── init.py                       # 知识库初始化脚本
├── Dockerfile                    # Docker 多阶段构建
├── docker-compose.yml            # Docker Compose 一键部署
├── .dockerignore                 # Docker 构建排除
├── .env.example                  # 环境变量模板
├── src/
│   ├── agent/                    # Agent 模块
│   │   ├── workflow.py           #   LangGraph ReAct 主工作流
│   │   ├── nodes.py              #   工作流节点
│   │   ├── tools.py              #   4 个 Agent 工具定义
│   │   └── state.py              #   状态定义与数据结构
│   ├── ingestion/                # 文档解析模块
│   │   ├── law_parser.py         #   法律文档结构化解析器
│   │   ├── chunker.py            #   按法律层级切分
│   │   └── indexer.py            #   ChromaDB 向量索引构建
│   ├── retrieval/                # 检索模块
│   │   ├── intent_router.py      #   意图识别与路由
│   │   ├── law_retriever.py      #   法条语义检索
│   │   ├── case_retriever.py     #   案例检索
│   │   ├── graph_retriever.py    #   图谱多跳检索
│   │   ├── bm25_retriever.py     #   BM25 关键词检索
│   │   ├── query_rewriter.py     #   查询改写
│   │   ├── reranker.py           #   CrossEncoder 重排序
│   │   ├── fusion.py             #   混合检索结果融合
│   │   └── context_compressor.py #   上下文压缩
│   ├── reasoning/                # 推理模块
│   │   ├── multi_hop.py          #   多跳法律推理
│   │   └── self_verify.py        #   法条引用自校验
│   ├── graph/                    # 图谱模块
│   │   ├── law_graph.py          #   法律知识图谱 (NetworkX)
│   │   └── builder.py            #   图谱构建
│   └── utils/                    # 工具模块
│       └── version_manager.py    #   法条版本管理
├── data/
│   ├── laws/                     # 示例法律文档
│   ├── cases/                    # 示例案例
│   └── chroma_db/                # 向量数据库（运行时生成）
├── docs/
│   └── blog-legal-rag.md         # 技术分享文章
└── tests/                        # 测试
    ├── test_structured_chunking.py
    ├── test_intent_router.py
    ├── test_multi_hop.py
    └── test_self_verify.py
```

## Roadmap

### 已完成

- [x] **v1.0** — 法律文档六级层级解析 + 结构化切分
- [x] **v1.1** — ChromaDB 向量检索 + BM25 混合检索
- [x] **v1.2** — 意图路由器（4 类法律意图分类）
- [x] **v1.3** — 法条引用知识图谱（NetworkX）+ 多跳 BFS 检索
- [x] **v1.4** — ReAct Agent 工作流（LangGraph）+ 4 工具
- [x] **v1.5** — 法条自校验 + 修正重试机制
- [x] **v1.6** — Streamlit 三栏布局 + FastAPI 7 端点
- [x] **v1.7** — Docker Compose 一键部署

### 进行中

- [ ] **v1.8** — 流式输出（SSE），改善长回答等待体验
- [ ] **v1.8** — 对话历史持久化（SQLite）

### 规划中

| 版本 | 季度 | 内容 |
|------|------|------|
| **v2.0** | 2026 Q3 | PDF/Word 法律文档直接上传解析；法条修订历史对比 |
| **v2.1** | 2026 Q4 | 裁判文书网数据接入，扩充案例检索覆盖面 |
| **v2.2** | 2027 Q1 | 多语言法律文本支持；类案检索与推荐 |
| **v3.0** | 2027 Q2 | 法律文书自动生成（起诉状/答辩状）；本地模型部署（vLLM） |

## Release

### v1.7.0 (2026-06-29)

- ✨ Docker Compose 一键部署支持
- 📝 技术博客：法律 RAG 自校验设计实践
- 📖 README 重构：架构图 / API 文档 / 项目目录

### v1.6.0 (2026-06-20)

- ✨ Streamlit 三栏布局（对话 | 检索过程 | 法条溯源）
- ✨ FastAPI 7 端点 + Lifespan 资源管理
- 🐛 修复长文本截断和暗色模式 CSS 错乱

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

## License

MIT License
