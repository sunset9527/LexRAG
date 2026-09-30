# LexRAG

> 面向中文法律信息检索的 RAG 平台：将法规、案例和自定义文档分别入库，提供可追溯的法条检索、相似案例检索与异步文档解析能力。

`FastAPI` · `Vue 3` · `LangGraph` · `MySQL` · `Redis / Celery` · `Chroma` · `BGE-M3`

> **免责声明**：LexRAG 提供法律信息检索与参考，不构成法律意见或律师服务。具体案件请结合事实、有效法律版本并咨询专业人士。

## 为什么是 LexRAG

通用 RAG 往往把法律条文、案例和用户上传文档混在同一个向量库中，既难以追溯，也容易在跨领域问题中引用错误材料。LexRAG 将法律数据按来源和知识库隔离，并保留原文定位、文件哈希与处理状态。

| 已验证成果 | 结果 |
|---|---:|
| 民法典法规库 | 1260 条法条，1636 个 chunks |
| 核心法规库 | 刑法、劳动法、劳动合同法、公司法、专利法、商标法、著作权法，7 个独立 collection |
| 年度案例库 | 10 本本地案例汇编，3661 页 OCR，623 条结构化案例与 623 条独立向量 |
| 文档解析端到端验收 | DOCX 上传后经 MySQL、Redis、Celery、Chroma 处理，得到 `READY`、492 字符、8 个 chunks、8 条向量 |
| 民法典检索评测 | 15 条自建法律咨询：BM25 13/15，向量 15/15，RRF 15/15 |

## 核心能力

### 多知识库法规检索

- 法规库 CRUD、状态展示与独立 Chroma collection；法规数据不会彼此混用。
- LawParser 按“编 → 章 → 节 → 条 → 款 → 项”解析，保留法律层级与条号。
- BGE-M3 语义检索、BM25 关键词检索与 RRF 融合；支持按法律领域/知识库范围检索。

### 案例库与相似案例

- 案例源保存本地路径、SHA-256、OCR 页数与处理状态；不将用户提供的年度案例汇编伪装为最高法指导案例。
- OCR 每 20 页写入检查点，支持中断恢复；结构化结果保存案由、案件焦点、裁判理由、结果和原始页码。
- 案例向量存于独立 `case_annual_2025` collection；相似案例以语义检索为基础，并对同案由候选加分。

### 文档解析中心

- 支持 PDF / DOCX 上传，保存原文件哈希、原始文件、标准化文本和来源位置。
- 任务状态：`UPLOADED → PARSING → CHUNKING → INDEXING → READY`；失败任务可重试。
- API 只负责入队；Redis + Celery Worker 在后台解析、分块并写入独立文档库。

### 法律问答与溯源

- LangGraph 工作流负责查询改写、意图识别、法规/案例检索、上下文压缩和答案生成。
- 前端将 LLM API Key、Base URL 和模型名通过请求头传入；本地 BGE-M3 不依赖外部 Embedding API。
- 回答生成依赖有效的 LLM API Key；未配置时，法规浏览、案例库和文档解析等数据能力仍可独立使用。

### v2.0 检索增强与质量兜底

- 原问题、多候选法律改写与 HyDE 假设文本分路召回，再经 RRF 融合；改写或 HyDE 失败会自动退回原问题检索。
- Redis 精确缓存与语义缓存默认 TTL 1 小时；缓存严格隔离授权作用域、知识库、模型和检索版本。语义命中会在聊天页明确显示原问题与相似度。
- 收藏保存问题、回答、引用、知识库和领域快照，并按 JWT 用户隔离。
- `data/evaluation/civil_code_baseline_15.jsonl` 是可审计的 15 条民法典回归基线；评测脚本报告真实样本数、Recall@K、MRR@K 与 NDCG@K，不将其表述为 50 条评测。

## 架构

```text
Vue 3 前端
  ├─ 法律咨询 / 法规浏览 / 知识库管理 / 案例库 / 文档解析中心
  │
FastAPI
  ├─ KnowledgeBaseService ────── MySQL（知识库与任务状态）
  ├─ CaseIngestionService ────── MySQL（案例来源与结构化案例）
  ├─ DocumentIngestionService ─ Redis → Celery Worker
  └─ LangGraph 法律问答工作流
       │
       ├─ Chroma：法规库、案例库、文档库的独立 collection
       ├─ BGE-M3：本地 Embedding（1024 维）
       └─ 外部 LLM：由前端 Settings 在运行时配置
```

## 快速开始（Windows）

### 前置条件

- Python 3.11+
- Node.js 18+
- MySQL（默认数据库名 `lexrag`）
- Redis（文档上传和 Celery Worker 必需）
- 本地 BGE-M3 模型；默认路径见 `config.py`

### 1. 安装依赖

```powershell
git clone https://github.com/sunset9527/LexRAG.git
cd LexRAG

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

### 2. 准备 MySQL 与 Redis

```powershell
# MySQL 中创建数据库（按你的本机账户调整）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS lexrag CHARACTER SET utf8mb4;"

# 使用 Docker 启动 Redis
docker run -d --name lexrag-redis -p 6379:6379 redis:7-alpine
```

如果容器已存在，可使用 `docker start lexrag-redis`。Redis 默认地址为 `redis://localhost:6379/0`。

### 3. 启动服务

```powershell
# 终端 1：FastAPI
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000

# 终端 2：Celery Worker
# Windows 使用 solo，避免 Celery prefork 子进程兼容问题
.\.venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker --pool=solo --loglevel=INFO

# 终端 3：Vue 前端
cd frontend
npm run dev
```

- 前端：`http://localhost:3000`
- OpenAPI：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

首次使用法律问答前，请在前端 **设置** 页面填入可用的 API Key、Base URL 与模型名。

## 数据与可追溯性

### 法规

模块 1 已接入 7 部核心法律。每份本地来源文件与清洗结果均记录 SHA-256、提取时间、实际条号范围和法条数，详见 `data/laws/raw/manifest.json`。

| 法规库 | 法条数 | chunks |
|---|---:|---:|
| 刑法 | 491 | 491 |
| 劳动法 | 107 | 156 |
| 劳动合同法 | 98 | 177 |
| 公司法 | 218 | 385 |
| 专利法 | 69 | 87 |
| 商标法 | 73 | 103 |
| 著作权法 | 61 | 145 |

### 案例

案例库数据来自用户提供的 2025 年度案例汇编。每条案例保存原始 PDF 页码范围，便于回到本地原文核验；来源标识为“用户提供的年度案例汇编”。

### 文档

上传文档以 SHA-256 去重；系统保留原文件路径、解析文本路径、分块参数、字符数与 chunk 数。自定义文档库的 collection 命名为 `kb_<slug>`，与法规和案例库隔离。

## 主要 API

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 服务健康状态 |
| `POST` | `/query` | 法律问答；可传 `X-API-Key`、`X-Base-URL`、`X-Model` |
| `GET / POST` | `/knowledge-bases` | 查询、创建法规知识库 |
| `DELETE` | `/knowledge-bases/{slug}` | 删除指定法规知识库 |
| `GET` | `/knowledge-bases/{slug}/laws` | 按知识库读取法规 |
| `GET` | `/case-sources` | 案例来源与 OCR 进度 |
| `GET` | `/cases` | 按领域、案由、来源筛选案例 |
| `GET` | `/cases/{id}/similar` | 相似案例检索 |
| `POST` | `/document-libraries` | 创建自定义文档库 |
| `POST` | `/document-libraries/{slug}/documents` | 上传 PDF / DOCX 并异步处理 |
| `GET` | `/documents/{id}` | 查询文档任务状态 |
| `GET / POST` | `/favorites` | 查询、创建当前用户的问答收藏 |
| `DELETE` | `/favorites/{id}` | 删除当前用户的一条收藏 |

完整接口定义请访问启动后的 `/docs`。

## 验证

```powershell
# v2.0：评测、查询扩展、缓存、收藏与既有回归
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider

# 前端生产构建
cd frontend
npm run build
```

评测候选文件模式（适合保存一次真实运行的排名后复算指标）：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  --dataset data\evaluation\civil_code_baseline_15.jsonl `
  --candidates path\to\ranked_candidates.json `
  --top-k 5 `
  --output eval_out\civil_code_baseline_15.json
```

`ranked_candidates.json` 的键为评测样本 ID，值为按排名排列的完整法条 ID 数组。任一样本缺少候选时命令会失败，以免把运行故障误报为指标下降。

历史模块验证：

```powershell
# 模块 3：案例解析、OCR、索引、检索、API
.\.venv\Scripts\python.exe -m pytest tests/test_case_parser.py tests/test_case_ocr.py tests/test_case_classifier.py tests/test_case_source_service.py tests/test_case_book_processor.py tests/test_annual_case_indexer.py tests/test_case_retrieval.py tests/test_case_api.py -q

# 前端生产构建
cd frontend
npm run build
```

已完成的模块级验证：

- 模块 1：法规接入与知识库 API 契约测试 25 项，7 个法规库真实数据校验。
- 模块 2：多知识库服务与 API 契约测试 13 项，前端生产构建。
- 模块 3：案例库 13 项测试；10 本案例真实 OCR、MySQL 入库和 Chroma 索引。
- 模块 4：22 项自动化测试；真实 DOCX 经 Redis、Celery、MySQL 与 Chroma 端到端验收。

## 项目结构

```text
LexRAG/
├─ api.py                       # FastAPI 入口与主要路由
├─ app/
│  ├─ models/                   # SQLAlchemy：知识库、案例、文档任务等
│  ├─ services/                 # 法规、案例、文档业务服务
│  └─ tasks/                    # Celery 任务
├─ src/
│  ├─ agent/                    # LangGraph 工作流
│  ├─ ingestion/                # 法条、案例、PDF/DOCX 解析与索引
│  ├─ retrieval/                # 法规/案例检索、BM25、RRF
│  └─ utils/                    # Embedding 工厂等
├─ frontend/                    # Vue 3 + TypeScript 前端
├─ scripts/                     # 法规、年度案例数据处理脚本
├─ data/                        # 运行期 Chroma、上传文档与解析产物
└─ tests/                       # 自动化测试
```

## 版本状态

v1.9 已完成法规接入、多知识库、案例库与文档解析中心四个模块。法条版本链（历史版本存档、按生效日期查询、逐条 diff）因现有本地资料缺少同一法律的第二版本而延期，后续将以真实历史文本补齐，不使用伪造差异数据。

v2.0 已完成代码与自动化回归：多候选改写、HyDE 融合、Redis 精确/语义缓存、收藏与 15 条基线评测数据契约均已进入仓库。最终指标需在本机真实 `kb_civil_code` 与 Redis 上执行上方命令后记录；在此之前不宣称 HyDE 的实际提升数值。

## License

本项目仅用于学习、研究与个人作品展示。请遵守所使用法律文本、案例资料与第三方模型服务的适用条款。
