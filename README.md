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
| v2.3 PDF 验收 | 文本层与扫描 PDF 均经真实 MySQL、Redis、Celery、Chroma 达到 `READY`；扫描页记录为 OCR 来源 |
| 民法典检索评测 | 15 条自建法律咨询：BM25 13/15，向量 15/15，RRF 15/15 |

## 最新迭代（2026-10-02）

本轮完成了前端现代企业 SaaS 视觉重构与工程化质量门禁接入：应用壳层、首页、法律咨询、登录注册及法规/图谱入口统一到轻量、证据优先的视觉体系；新增一键质量门禁、覆盖率报告、GitHub Actions 与真实数据口径说明。完整变更、验证数据、已知警告与复跑方法见 [本轮迭代记录](docs/iterations/2026-10-02-v30-frontend-quality-iteration.md) 和 [工程质量说明](docs/engineering-quality.md)。

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

- v2.1 使用固定节点的证据驱动工作流：结构化拆解、可预测路由、法规/案例/图谱检索、证据账本、回答生成与引用校验；不采用多 Agent 自主协作。
- 回答只能引用本次、当前知识库中进入证据账本的法条。伪造条号、法律名称不匹配、缺少引用或校验异常均不能通过；最多进行一次基于同一证据的受控修复。
- 聊天页可展开查看脱敏的节点时间线、耗时、检索数量和校验结论，不显示 Prompt、API Key、用户原文或模型思维链。
- 前端将 LLM API Key、Base URL 和模型名通过请求头传入；本地 BGE-M3 不依赖外部 Embedding API。
- 回答生成依赖有效的 LLM API Key；未配置时，法规浏览、案例库和文档解析等数据能力仍可独立使用。

### v2.2 法律场景工作台

- 合同 PDF/DOCX 或文本审查：按条款识别违约金、免责、格式条款和管辖风险；风险只标为“需人工核验”，并附本次检索且校验通过的法条。
- 劳动用工/公司治理合规检查：规则映射到对应的 `labor-law` / `company-law` 知识库；跨知识库证据不会被引用。
- 提供起诉状、答辩状、仲裁申请书、律师函、合同五类受控模板，以及劳动/合同/侵权路径图（节点、转移条件、材料和检索范围）。
- 场景任务由 Redis + Celery 持久化处理；合同建议仅在证据校验后，通过浏览器临时 API Key 生成，密钥不进入数据库或消息队列。
- 报告按“摘要、风险、法条、参考案例、建议、提示”结构生成并可下载 PDF。

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
  └─ 证据驱动法律工作流
       │
       ├─ 拆解 / 路由 → 并行检索 → 证据账本 → 回答 → 规则校验 → 一次受控修复
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

## v3.0 本机 Docker 演示

`docker-compose.v3.yml` 将 Vue/Nginx、API、Celery Worker/Beat、MySQL、Redis、Prometheus 与 Grafana 放在私有网络；浏览器、Prometheus、Grafana 端口仅绑定本机。首次启动需设置一个仅用于本机的 JWT 密钥：

```powershell
$env:JWT_SECRET_KEY = "replace-with-a-long-random-local-secret"
$env:MCP_HTTP_BEARER_TOKEN = "replace-with-another-random-local-secret"
docker-compose -f docker-compose.v3.yml up --build
```

- 业务前端：`http://127.0.0.1:8080`
- Prometheus：`http://127.0.0.1:9090`
- Grafana：`http://127.0.0.1:3000`（首次登录使用容器默认管理员凭据后立即修改）
- API 指标：仅 Docker 内网 `http://api:8000/metrics`，由 Prometheus 抓取，不对宿主机暴露。

启动后用管理员账号登录，在“组织管理”中确认本机演示组织。问答、知识库与法规更新请求会按 JWT 用户的组织角色授权；`X-Organization-ID` 只是在用户有多个组织时选择已有成员关系，不能提升权限。审计仅保存问题/答案哈希、长度、请求 ID、校验状态与缓存标记，不保存原问题、原答案、模型 Token 或 API Key。

### MCP（可选）

默认命令为 stdio，适合桌面客户端：

```powershell
docker-compose -f docker-compose.v3.yml run --rm -T `
  -e MCP_DEMO_USER_ID=你的用户ID `
  -e MCP_DEMO_ORGANIZATION_ID=你的组织ID `
  mcp python -m app.mcp_server
```

如需本机 Streamable HTTP，明确选择 profile，并把服务账号绑定到已存在的低权限组织成员；它仅映射至 `127.0.0.1:8001/mcp`，同时校验 `Host` 与 `Origin`：

```powershell
$env:MCP_DEMO_USER_ID = "你的用户ID"
$env:MCP_DEMO_ORGANIZATION_ID = "你的组织ID"
$env:MCP_HTTP_BEARER_TOKEN = "换成一段随机本机密钥"
docker-compose -f docker-compose.v3.yml --profile mcp-http up mcp-http
```

MCP 只提供本地法规只读检索、非权威概念检索与更新状态查看；不提供写入、自动入库或绕过来源网站限制的抓取。

法规更新的 Beat 任务每 15 分钟检查可选的本地快照卷。它只读取 `/app/data/law_snapshots/{订阅ID}.txt`，哈希变化仅生成 `PENDING_REVIEW` 事件。管理员确认后，若订阅关联法规知识库，Worker 会先在带版本哈希的新 collection 中完成索引，成功后才切换查询指针；失败时当前 `READY` collection 保持不变。

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

### 工程化质量门禁

一条命令会顺序运行后端回归、前端契约测试和前端生产构建，并将**真实退出码、耗时、截断日志及后端覆盖率**写入本地报告。报告目录被 Git 忽略，不会把运行时 Key 或用户咨询内容提交进仓库。

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
```

输出：

- `reports\quality\latest.json`：机器可读的质量门禁结果；
- `reports\quality\latest.md`：人工可读的门禁摘要；
- `reports\quality\coverage.json`：`app/` 与 `src/` 的后端行覆盖率明细。

2026-10-02 的本机基线为：后端 **220** 项测试、前端 **3** 项契约测试、生产构建均通过；后端覆盖 **4,208 / 6,430** 行（**65.44%**）。该数字会随代码和测试变化，提交或演示前请以上述命令重新生成，不把它当作永久承诺。

```powershell
# v2.0：评测、查询扩展、缓存、收藏与既有回归
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider

# 前端生产构建
cd frontend
npm run build
```

直接对真实 Chroma collection 运行 15 条基线：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  --dataset data\evaluation\civil_code_baseline_15.jsonl `
  --live-collection kb_civil_code `
  --persist-directory data\chroma_db `
  --top-k 5 `
  --output eval_out\civil_code_baseline_15.json
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

当前 `civil_code_baseline_15.json` 是同一份人工复核的 15 条民法典基线的真实结果：Recall@5 **1.0000**、MRR@5 **0.9667**、NDCG@5 **0.9754**。它只代表这 15 条已标注样本，不能外推为泛化法律问答正确率。

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
│  ├─ agent/                    # 历史 ReAct 实现（兼容保留）
│  ├─ workflow/                 # v2.1 证据账本、规则校验与固定节点工作流
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

v2.0 已完成代码、自动化与真实环境验收：多候选改写、HyDE 融合、Redis 精确/语义缓存、收藏与 15 条基线评测数据契约均已进入仓库。2026-09-30 在真实 `kb_civil_code` 上运行基础向量检索基线，得到 **Recall@5=1.000000、MRR@5=0.966667、NDCG@5=0.975395**；报告见 `eval_out/civil_code_baseline_15.json`。真实 Redis 也已验证精确/语义命中、3600 秒 TTL 与故障旁路。该指标不被表述为 HyDE 提升；HyDE 对照实验需另以有效运行时 LLM Key 执行。

v2.1 已完成证据驱动工作流与真实冷缓存验收。2026-10-01 使用本机 `kb_civil_code`、Redis、MySQL 和运行时 LLM 对 15 条人工标注民法典基线执行 `/query`：**校验通过率 1.000000、标注法条覆盖率 1.000000、缓存命中 0/15、平均端到端延迟 18,978.205ms**，详见 `eval_out/workflow_civil_code_baseline_15_20261001.json`。报告明确记录：断言支持率尚无人工复核，不能以引用存在性替代法律效果结论。

v2.2 已完成合同审查、劳动/公司合规检查、文书模板、维权路径图、结构化 PDF、Vue 工作台、Celery 场景调度与 Alembic 迁移。2026-10-01 在本机环境真实提交合同、劳动合规和维权路径任务：三类任务均达到 `READY`，合同识别 2 项风险且证据已验证，劳动合规识别 2 项风险且证据已验证，劳动路径返回 4 个图节点；PDF 下载返回 `application/pdf`。自动化回归为 **156 项通过**，前端生产构建通过。场景规则结果仍是法律信息参考，正式法律效果应由人工用完整事实样本复核。

v2.3 已完成 PDF 富解析、OCR 回退、批量入队、页级来源、结构化结果与关系 API。2026-10-01 在本机 MySQL、Redis、Celery、API 与 Vue 代理环境中，以仓库可复核的文本层 PDF 和扫描 PDF 验收：两份样本均独立进入 `READY`，文本页来源为 `text`，扫描页来源为 `ocr`。样本没有人工字符/字段/表格/关联标注，因此相关准确率与确认率保持为空；不把 OCR 成功处理表述为 OCR 准确率。

v2.4 已采用既有 MySQL 实现会话持久化、最近 5 轮受控上下文、用户画像、规则型推荐及 Vue 会话管理，不新增 PostgreSQL / PostgresSaver。数据库迁移已到 `20261001_03`；两账号真实验证了会话创建、重命名、搜索、归档，以及跨用户和归档会话的 `/query` 均被拒绝。运行时未配置 LLM Key，因此真实多轮回答的记忆注入与引用约束仍待验收。

## License

本项目仅用于学习、研究与个人作品展示。请遵守所使用法律文本、案例资料与第三方模型服务的适用条款。
