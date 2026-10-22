# LexRAG｜证据驱动的法律 RAG 平台

> 面向中文法律信息检索的 RAG 工程项目：将法规、案例和用户文档分库检索，要求每一条法律引用都能回到本轮证据与原文位置。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)
![Tests](https://img.shields.io/badge/Backend%20tests-300%20passed-2ea44f)

> **法律信息免责声明**：项目用于法律信息检索与学习展示，不构成法律意见。具体案件需要结合完整事实、法律时效并咨询专业人士。

## 我解决的核心问题

法律问答最危险的不是“没答上”，而是回答看似合理却引用错误法律、错误知识库，或无法追溯来源。

LexRAG 建立一条可检查的证据链，而不是把所有材料混进一个向量库：

```text
用户问题 → 路由与知识库范围确定 → 独立检索
→ Evidence Ledger（本轮证据账本）→ LLM 回答
→ Citation Verifier 校验条号、法律名与证据归属 → 引用原文
```

伪造条号、跨知识库引用、法律名称不匹配，或不在本轮证据账本中的引用都会被拒绝；失败时最多基于同一批证据进行一次受控修复。

## 内容速览

| 维度 | 可验证事实 |
| --- | --- |
| 法规数据 | 仓库包含民法典及刑法、劳动法、劳动合同法、公司法、专利法、商标法、著作权法 8 部法规文本；民法典历史入库记录为 **1,260** 条、**1,636** 个 chunks，权威来源与版本链仍待阶段 4 收口 |
| 当前主链 | `/query` 调用共享编译的 LangGraph `StateGraph`：规划、路由、检索、证据账本、回答、引用校验和最多一次受控修复；依赖通过请求级 context 传入 |
| 评测状态 | 15 条民法典数据仅保留为历史回归基线；八部法律 100 条快照中有 85 条缺少逐条人工审核记录，相关报告只作临时工程记录，不作为正式效果指标 |
| 案例与文档 | 10 本本地案例汇编、3,661 页 OCR、623 条结构化案例；PDF/DOCX 支持异步解析与页级来源 |
| 工程质量 | Stage 2 代码基线 `9c9313b`：2026-10-22 在普通 Windows PowerShell 完整运行后端 **300 passed**、4 条依赖弃用警告；前端 **4 passed**，Ruff、Vue 类型检查和生产构建通过 |

历史 15 条本机记录曾得到 Recall@5 1.0000、MRR@5 0.9667、NDCG@5 0.9754；证据工作流记录曾得到引用校验通过率 1.0000、标注法条覆盖率 1.0000、平均端到端延迟 18,978ms。它们来自 2026-10-01 的未冻结工作树，缺少可对应的代码提交和保留报告，因此不作为当前 Release 指标。法律结论的人审支持率尚未形成正式指标。

## 核心技术闭环

### 多知识库混合检索

- 法规、案例和自定义文档拥有独立 Chroma collection，查询从源头限制知识库范围。
- BGE-M3 本地向量检索与 BM25 并行召回，经 RRF 融合；条号问题使用精确条号增强。
- 原问题、多候选法律改写与 HyDE 分路召回；增强失败自动回退原问题。
- 法规解析保留“编 → 章 → 节 → 条 → 款 → 项”结构、法律名称、条号与相互引用。

### 证据驱动回答

- 当前主链是显式 LangGraph `StateGraph`：拆解、路由、检索、证据聚合、回答、校验、一次受控修复和证据不足终止均对应独立节点与条件边。
- Evidence Ledger 按来源与知识库记录证据，阻断跨库、跨会话或跨用户的引用穿透。
- Citation Verifier 校验回答引用真实存在于本轮账本，并返回可定位原文。
- 最近 5 轮会话记忆仅作为非证据上下文，不能绕过当前轮证据门控。
- `src/agent/` 中的 ReAct 实现是遗留教学链路，不承载当前 `/query`；当前主链位于 `src/workflow/legal_evidence_workflow.py`。

### 可追溯文档与案例处理

- PDF/DOCX 经 Redis + Celery 异步处理：`UPLOADED → PARSING → CHUNKING → INDEXING → READY`。
- 原始文件 SHA-256 去重，页码、段落、表格/OCR 来源与结构化抽取结果均可回溯。
- 案例库保存来源、OCR 检查点、案由、裁判理由、结果与页码；相似案例不会混入法规库。

### 安全、权限与隐私边界

- 浏览器会话使用 HttpOnly Cookie；Bearer Token 继续保留给 CLI。BYOK API Key 只保存在当前页面内存，不进入 localStorage、数据库、日志或审计元数据。
- 运行时模型地址默认受 allowlist 约束；自定义地址需要权限，并拒绝本机、私网、链路本地、云元数据、危险端口和重定向。
- 图谱、案例、上传、文档、会话、Prompt 与推荐链路均执行认证、权限和组织归属检查；遗留 `/verify/{query_id}` 与进程级结果表已删除。
- 上传执行分块大小限制、扩展名/MIME/魔数一致性检查、DOCX 解压限制、组织/知识库目录隔离、PDF 页数与抽取字符上限，以及 Celery 软/硬超时。
- 原始咨询和异常文本不写常规日志；对外 500 使用稳定错误包络，敏感管理动作只追加操作者、组织、资源 ID、结果和 request ID 等脱敏审计元数据。

## 技术架构

```text
Vue 3 + TypeScript
  └─ 咨询工作台 / 引用原文 / 法规浏览 / 知识库 / 文档与案例管理
                 │
FastAPI ── LangGraph StateGraph：路由 → 混合检索 → Evidence Ledger → 回答 → 引用校验
  ├─ MySQL：用户、知识库、任务、会话、审计元数据
  ├─ Redis → Celery Worker：PDF/DOCX/案例异步处理
  └─ Chroma：法规 / 案例 / 文档独立向量集合

本地模型：BGE-M3 Embedding（1024 维）
```

`Python` · `FastAPI` · `LangGraph` · `Chroma` · `BGE-M3` · `MySQL` · `SQLAlchemy/Alembic` · `Redis` · `Celery` · `Vue 3` · `TypeScript` · `Docker` · `Prometheus/Grafana`

## 快速开始（Windows）

环境：Python 3.11+、Node.js 18+、MySQL、Redis，以及本地 BGE-M3 模型（默认路径见 `config.py`）。

```powershell
git clone https://github.com/sunset9527/LexRAG.git
cd LexRAG
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend; npm install; cd ..
```

```powershell
# 终端 1：API
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000

# 终端 2：Windows 下使用 solo worker
.\.venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker --pool=solo --loglevel=INFO

# 终端 3：前端
cd frontend; npm run dev
```

- 前端：`http://localhost:3000`
- OpenAPI：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

法律问答需在前端“设置”页填写可用的 LLM API Key、Base URL 和模型名；法规浏览、案例库、文档处理和离线评测不依赖该 Key。

生产环境先关闭开放注册并显式初始化管理员。密码仅通过进程环境传入，不接受命令行参数：

```powershell
$env:APP_MODE = 'production'
$env:OPEN_REGISTRATION = 'false'
$env:AUTH_COOKIE_SECURE = 'true'
$env:JWT_SECRET_KEY = '<至少 32 字符的随机值>'
$env:LEXRAG_BOOTSTRAP_USERNAME = 'admin'
$env:LEXRAG_BOOTSTRAP_PASSWORD = '<强密码>'
python scripts\bootstrap_admin.py
```

## 可复现验证

```powershell
# Ruff → 后端测试与覆盖率 → 前端契约测试 → 前端生产构建
.\.venv\Scripts\python.exe scripts\quality_gate.py
```

质量报告写入本地 `reports/quality/`（已 Git 忽略），包含真实命令、退出码、耗时和覆盖率，不记录 API Key 或用户咨询原文。

Stage 2 的已执行命令、结果和未覆盖边界见 [`docs/status/stage-2-security-verification.md`](docs/status/stage-2-security-verification.md)。

```powershell
# 在真实 Chroma collection 上复现 15 条民法典检索基线
.\.venv\Scripts\python.exe scripts\evaluate_retrieval.py `
  --dataset data\evaluation\civil_code_baseline_15.jsonl `
  --live-collection kb_civil_code `
  --persist-directory data\chroma_db `
  --top-k 5 `
  --output eval_out\civil_code_baseline_15.json
```

## 项目结构

```text
LexRAG/
├─ api.py                 # FastAPI 入口与主要路由
├─ app/                   # 认证、权限、数据模型、业务服务、Celery 任务
├─ src/
│  ├─ workflow/           # 证据账本、引用校验、LangGraph StateGraph 主链
│  ├─ retrieval/          # 法规/案例检索、BM25、RRF、改写与重排
│  ├─ ingestion/          # 法条、案例、PDF/DOCX 解析与索引
│  └─ evaluation/         # 可复现检索评测
├─ frontend/              # Vue 3 + TypeScript
├─ scripts/               # 质量门禁、处理与评测脚本
├─ tests/                 # 当前 Stage 2 质量基线收集 300 项后端自动化测试
├─ infra/                 # Prometheus / Grafana 配置
└─ docker-compose.v3.yml  # 本机企业化演示编排
```

## 设计边界

- 15 条评测不被夸大为通用法律问答正确率。
- 100 条八部法律快照存在批量 `approved` 与“待人工核验”冲突，已明确降级为临时工程记录；修正前不对外引用其指标。
- OCR/文档解析已完成真实处理链路验收，但没有人工逐页字符和表格标注，因此不宣称 OCR 准确率。
- Compose 已通过静态解析；Docker 冷启动与浏览器人工端到端验收仍待在可用本机环境完成。
- Stage 2 的安全代码和完整后端自动化已经收口；真实多组织攻击性验收、受控 SSRF/DNS 重绑定实验及 Docker 冷启动证据仍分别留在阶段 8 和阶段 3，因此当前版本仍不表述为生产可用。

## License

本项目仅用于学习、研究与个人作品展示。请遵守法律文本、案例资料及第三方模型服务的适用条款。
