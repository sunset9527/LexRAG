# LexRAG 阶段 3：可复现部署与运行时基础设施收口实施计划

**设计依据：** `docs/superpowers/specs/2026-10-22-stage-3-reproducible-deployment-design.md`  
**计划状态：** 已生成，待用户批准执行  
**实施基线：** `a388687`  
**目标：** 在不改变法律检索算法、Prompt 语义和评测数据的前提下，使全新环境通过单一 Compose 完成迁移、八库初始化、启动、健康检查和恢复验证。

## 实施约束

- 使用测试先行：先建立失败契约，再写最小实现，最后运行聚焦回归。
- 每个提交只包含一个可解释的部署关注点。
- 不直接修改或清空用户现有 MySQL、Chroma、Redis、上传目录和 Docker volume。
- Docker 验收使用固定的独立 project name 和专用 volume。
- 不运行阶段 8 的正式法律效果评测，不修改任何评测问题、标签或历史指标。
- 不推送远端，不改写 Git 历史。
- 外部 `RAG法律.md` 只有在真实验收完成后才标记阶段 3 为 100%。

## 目标文件布局

计划新增或重点修改：

```text
compose.yaml
Dockerfile
.dockerignore
.env.example
.env.docker.example
.python-version
.nvmrc
requirements.txt
constraints-py313.txt

config.py
api.py
app/db/session.py
app/models/knowledge_base.py
app/services/deployment_bootstrap_service.py
app/services/readiness_service.py
app/tasks/celery_app.py

src/ingestion/statute_catalog.py
src/ingestion/index_identity.py
src/ingestion/indexer.py
src/utils/embedding_factory.py

scripts/bootstrap_runtime.py
scripts/check_worker_health.py
scripts/verify_deployment.py

alembic/versions/20260930_00_initial_schema.py
alembic/versions/20261022_01_add_index_identity.py

frontend/Dockerfile
frontend/nginx.conf

tests/test_deployment_settings.py
tests/test_embedding_contract.py
tests/test_alembic_contract.py
tests/test_statute_catalog.py
tests/test_deployment_bootstrap.py
tests/test_readiness.py
tests/test_compose_contract.py
tests/test_nginx_contract.py

docs/deployment.md
docs/status/stage-3-deployment-verification.md
```

具体实施时允许根据已有模块边界微调文件名，但不得把数据库迁移、bootstrap 和健康检查重新塞回 `api.py` 的单一大函数。

## Task 1：统一运行时版本和依赖锁

### 目标

先证明目标 Python/Node 版本能够安装完整依赖并加载关键原生模块，再冻结版本；避免先写完 Compose，最后才发现 PyTorch、ONNX Runtime 或 Chroma 无可用 wheel。

### 测试先行

新增 `tests/test_deployment_settings.py` 的静态契约：

- Python 版本文件、Dockerfile 和文档引用同一主次版本；
- Node 版本文件、前端 Dockerfile 和文档引用同一主版本；
- `requirements.txt` 包含 `PyMySQL`；
- 不再包含未使用的 `psycopg2-binary`、`pgvector` 和重复依赖；
- Docker 安装命令使用 constraints；
- 前端镜像使用 `npm ci`，而不是 `npm install`。

先运行并确认测试因当前文件不一致而失败：

```powershell
python -m pytest tests\test_deployment_settings.py -q
```

### 实现

1. 用当前 Stage 2 已验证环境列出所有直接依赖和实际解析版本。
2. 在目标 Linux Python 3.13 容器中完成一次兼容性探测，至少导入：`torch`、`sentence_transformers`、`onnxruntime`、`chromadb`、`langgraph`、`fitz`、`rapidocr_onnxruntime`、`pymysql`。
3. 若 Python 3.13 探测全部通过，则统一固定为 Python 3.13；若原生依赖确有不可解决的兼容阻塞，整体改用经过同等验证的单一版本，并同步本机说明、Docker 和质量门禁。
4. 整理 `requirements.txt` 为唯一直接依赖清单，增加 `PyMySQL`，删除重复项和无调用依赖。
5. 生成 `constraints-py313.txt`（若最终版本不同则相应改名），精确锁定所有传递依赖。
6. 增加 `.python-version`、`.nvmrc`，固定 Docker 基础镜像补丁版本。
7. 前端 Dockerfile 改为复制 `package.json` 与 `package-lock.json` 后执行 `npm ci`。

### 验证

```powershell
python -m pytest tests\test_deployment_settings.py -q
python -m pip check
cd frontend
npm ci
npm run build
cd ..
```

### 提交

```text
build(stage-3): lock reproducible runtime dependencies
```

## Task 2：建立真正可从零执行的 Alembic 迁移链

### 目标

让空 MySQL 不依赖 `Base.metadata.create_all()` 即可完整迁移到 head，同时保护已有开发库升级路径。

### 测试先行

新增 `tests/test_alembic_contract.py`：

- `app/db/session.py` 不得调用 `Base.metadata.create_all()`；
- Alembic 只有一个 root 和一个 head；
- 当前首个业务迁移必须依赖新的基础 schema revision；
- 基线迁移包含所有历史基础表；
- ORM 已注册表集合与最终迁移 schema 不存在未解释缺口；
- API lifespan 不承担迁移职责。

静态契约先失败后，再补真实 MySQL 集成验证脚本。

### 实现

1. 将 `init_db()` 收缩为 Engine 和 Session factory 初始化。
2. 汇总 `app/models/` 的完整表、外键、索引、唯一约束和 server default。
3. 新建 `20260930_00_initial_schema.py`，创建当前首个迁移之前已存在的基础表。
4. 将 `20261001_01_add_scenario_jobs.py` 的 `down_revision` 指向新基线。
5. 新建 `20261022_01_add_index_identity.py`，为 `knowledge_bases` 增加：
   - `source_hash`；
   - `embedding_fingerprint`；
   - `index_schema_version`；
   - 必要的非敏感构建状态字段。
6. 保持现有数据库 head 可继续升级到新 revision；不修改已发布 revision 的业务内容，只调整原 root 的父 revision。
7. 为失败迁移补充文档化恢复方法：备份、查看 current/history、修复后重跑；不提供自动 destructive downgrade。

### 真实 MySQL 验证

使用两个临时数据库：

- `lexrag_stage3_empty`：从空库执行 `alembic upgrade head`；
- `lexrag_stage3_upgrade`：从用户开发库的只读 schema/data 副本验证升级。

验证命令由后续部署脚本统一封装，核心检查为：

```powershell
alembic heads
alembic current
alembic upgrade head
```

不得对用户现有 `lexrag` 数据库执行 drop、truncate 或 downgrade。

### 提交

```text
refactor(stage-3): make alembic the only schema initializer
```

## Task 3：显式化 Embedding provider、维度和索引身份

### 目标

消除 Windows 路径依赖、隐式远程回退和不同模型混写 collection 的风险。

### 测试先行

新增 `tests/test_embedding_contract.py`，覆盖：

- `local` provider 缺少模型目录时失败；
- `zhipu` provider 缺少 Key 时失败；
- 本地加载失败不会转用远程 provider；
- 实际向量维度与配置不一致时失败；
- fingerprint 对同一配置稳定，对 provider、模型、维度、normalize 和 schema version 变化敏感；
- 全局缓存不会跨 fingerprint 复用实例；
- 错误消息只列配置名和稳定错误码，不包含 Key 或宿主机敏感路径。

### 实现

1. 在 `config.py` 增加：
   - `embedding_provider: Literal["local", "zhipu"]`；
   - 容器默认模型路径；
   - normalize、维度和 index schema version；
   - `development/demo/production` 三种运行模式。
2. 重写 `src/utils/embedding_factory.py`：
   - 根据 provider 单路径加载；
   - provider 失败即失败；
   - 使用 fingerprint 作为缓存身份；
   - 提供不暴露秘密的诊断结果。
3. 新增 `src/ingestion/index_identity.py`，集中计算和比较 fingerprint。
4. 修改 `LawIndexer` 和文档/案例 indexer：创建与打开 collection 时写入或校验 metadata；维度/fingerprint 不一致时抛出专用异常。
5. 为历史无 metadata collection 提供显式迁移/重建提示，不自动猜测兼容。

### 验证

```powershell
python -m pytest tests\test_embedding_contract.py tests\test_law_indexer_search.py tests\test_document_ingestion_service.py tests\test_annual_case_indexer.py -q
python -m ruff check config.py src\utils\embedding_factory.py src\ingestion app\services tests\test_embedding_contract.py
```

### 提交

```text
feat(stage-3): enforce embedding and index identity
```

## Task 4：统一八部法规目录并实现幂等 bootstrap

### 目标

让民法典和其余七部法规共享同一个可校验目录，通过内容哈希和 Embedding fingerprint 决定跳过、构建或切换。

### 测试先行

新增 `tests/test_statute_catalog.py`：

- 目录恰好包含八部法规；
- slug、名称和文本路径唯一；
- 文件存在且 SHA-256 与 manifest 一致；
- 预期法条数、首末条号与解析结果一致；
- 目录不依赖 `E:\...` 等宿主机绝对路径。

新增 `tests/test_deployment_bootstrap.py`：

- 空库首次初始化成功；
- 相同 source hash + fingerprint 第二次执行为 skipped；
- source hash 或 fingerprint 变化时构建新版本 collection；
- 新 collection 校验失败时不切换旧 DB 指针；
- 并发或重复运行不能同时切换同一知识库；
- 单部法规失败不把它错误标记 READY；
- 最终摘要只包含 slug、状态、计数、哈希摘要和稳定错误码。

### 实现

1. 新建 `src/ingestion/statute_catalog.py`，统一八部法规定义。
2. 补充民法典 manifest 项；只记录当前已有清洗文本的可复核哈希和解析事实，不增加未经证实的权威性声明。
3. 让 `scripts/ingest_statutes.py` 和 `scripts/rebuild_civil_code_knowledge_base.py` 复用目录；旧入口可以保留为兼容包装器，但不能再维护独立定义。
4. 新建 `DeploymentBootstrapService`，提供：
   - 基础 RBAC/Prompt seed；
   - 可选管理员 bootstrap；
   - 八库逐库校验和隔离构建；
   - collection 验证与原子指针切换；
   - 图谱重建/验证；
   - 机器可读摘要。
5. collection 使用可追溯名称，至少包含 slug 和 source/index identity 摘要；正在构建的 collection 不作为 READY 指针。
6. 运行时 BM25 仍从当前活动 collection 构建内存索引；bootstrap 对 Chroma 数据完整性进行预验证，不引入新的持久化 BM25 格式。
7. 新建 `scripts/bootstrap_runtime.py` 作为唯一命令行入口，支持全量、单库、只验证和 JSON 报告模式。
8. 从 API lifespan 移除 Prompt seed 和其他 bootstrap 动作。

### 验证

```powershell
python -m pytest tests\test_statute_catalog.py tests\test_deployment_bootstrap.py tests\test_statute_ingestion.py tests\test_knowledge_base_service.py tests\test_law_graph_rebuild.py -q
python -m ruff check src\ingestion\statute_catalog.py app\services\deployment_bootstrap_service.py scripts\bootstrap_runtime.py tests\test_statute_catalog.py tests\test_deployment_bootstrap.py
```

### 提交

```text
feat(stage-3): add idempotent eight-law bootstrap
```

## Task 5：拆分 API 生命周期并实现真实 readiness

### 目标

API 不再创建遗留空 `law_articles` collection，也不因组件字典非空就报告 healthy。

### 测试先行

新增 `tests/test_readiness.py`，覆盖：

- `/health/live` 始终只反映进程存活；
- `/health/ready` 全部通过时返回 200；
- 数据库失败、revision 落后、Redis 失败、Embedding 失败、图谱失败、缺库、非 READY、collection 缺失、哈希不符、fingerprint 不符分别返回 503；
- `/health` 与 readiness 兼容；
- 响应不包含数据库 URL、Key、绝对路径或异常文本；
- Prometheus、Grafana和运行时 LLM Key 缺失不影响 readiness；
- API lifespan 不执行 seed、migration 或 index rebuild。

### 实现

1. 新建 `ReadinessService`，把每项探针定义为独立、可注入、带超时的检查。
2. API lifespan 执行：安全配置校验、数据库连接工厂初始化、运行时服务装配；严格模式下关键装配失败不能被吞掉。
3. 删除 `initialize_components()` 中对默认 `settings.law_collection_name` 的 `LawIndexer`、`LawRetriever` 和 BM25 初始化。
4. 保留现有 `/query` 按已授权知识库活动 collection 构造 scoped indexer 的语义，不修改阶段 5 的单库限制和检索算法。
5. 将可选案例库、缓存和观测组件按明确的硬/软依赖策略装配；失败状态进入 readiness 或 degradation，而不是只靠日志猜测。
6. 新增三个健康端点并让 Docker 使用 `/health/ready`。

### 验证

```powershell
python -m pytest tests\test_readiness.py tests\test_query_cache_api.py tests\test_evidence_workflow.py tests\test_route_security_contract.py -q
python -m ruff check api.py app\services\readiness_service.py tests\test_readiness.py
```

### 提交

```text
feat(stage-3): expose dependency-aware readiness
```

## Task 6：收敛 Dockerfile、单一 Compose 和数据卷

### 目标

形成唯一可执行拓扑，并确保迁移、bootstrap、API、Worker 和前端之间的依赖关系由 Compose 表达。

### 测试先行

新增 `tests/test_compose_contract.py`，使用 YAML 解析和 `docker compose config` 输出验证：

- 仓库只有一个权威 Compose 入口；
- 默认服务完整；
- migrate/bootstrap 是一次性服务；
- API 依赖 migrate/bootstrap 成功；
- MySQL、Redis、API 不默认暴露宿主机端口；
- MCP 在 profile 下；
- 模型只读挂载；
- 法规 seed 文件不会被运行时 volume 遮蔽；
- API、Worker、Beat 和 bootstrap 使用同一数据库、Redis、Embedding 和持久化路径；
- JWT、MySQL 密码没有演示默认值；
- API healthcheck 使用 readiness，不能把 HTTP 200 的 initializing 当 healthy。

### 实现

1. 新建根目录 `compose.yaml`，合并现有两份配置。
2. MySQL 创建普通应用账号；所有业务容器使用应用账号连接。
3. 定义 `migrate`、`bootstrap` 的 completed-successfully 依赖。
4. 增加 BGE-M3 Windows 宿主机路径变量，容器目标固定为 `/models/bge-m3`。
5. 重设运行目录：法规源文件只读，Chroma、上传、快照、图谱产物分别挂载。
6. Dockerfile 删除 Streamlit target，只保留共同 base/dependencies/runtime/API 目标；确保非 root 用户能写所有运行目录。
7. 增加 `.dockerignore`，排除 `.git`、`.venv`、node_modules、现有 Chroma、本地上传、日志、报告和密钥文件。
8. 增加 `.env.docker.example`，用变量名和说明表达必填配置，不含真实密钥。
9. 在新入口通过静态与真实验证后，删除旧的两份 Compose，避免继续被误用。

### 验证

```powershell
python -m pytest tests\test_compose_contract.py -q
docker compose --env-file .env.docker.stage3 config --quiet
docker compose --env-file .env.docker.stage3 build
```

删除旧 Compose 前再次确认 README、脚本和 CI 没有引用旧文件名。

### 提交

```text
build(stage-3): consolidate reproducible compose stack
```

## Task 7：收口 Worker、Beat 与 Nginx 运行契约

### 目标

证明异步任务队列实际可达，并保持前端现有 `/api` rewrite 语义。

### 测试先行

新增 `tests/test_nginx_contract.py` 和 Worker 探针测试：

- `/api/query` 被转发为后端 `/query`；
- 报告下载等直接 URL 继续可用；
- 上传上限与应用层一致；
- 有合理的连接/读写超时、安全响应头、gzip 和静态缓存；
- 流式代理关闭 buffering，但不新增 SSE 路由；
- Worker 探针必须连接 broker 并定位当前节点，进程存在不足以判定 healthy；
- Windows 文档使用 `--pool=solo`，容器命令不照搬 Windows 配置。

### 实现

1. 更新 `frontend/nginx.conf`，保留 trailing-slash `proxy_pass` 所形成的 `/api` 前缀移除行为。
2. 为未来流式接口配置 `proxy_buffering off`、`X-Accel-Buffering` 等代理约束，但不实现阶段 6 API。
3. 新增 `scripts/check_worker_health.py`，通过 broker/inspect 验证目标 worker 响应；不打印 broker 凭据。
4. 为 Celery 配置稳定 worker hostname、任务时间限制和健康检查超时。
5. Beat 使用独立 pid/schedule 路径，避免只读或共享文件冲突；其失败不伪装为 healthy。

### 验证

```powershell
python -m pytest tests\test_nginx_contract.py tests\test_document_task_security.py tests\test_legal_scenarios.py -q
docker compose --env-file .env.docker.stage3 config --quiet
```

### 提交

```text
fix(stage-3): harden proxy and worker health contracts
```

## Task 8：建立可复现的部署验收脚本

### 目标

把冷启动、幂等、恢复和故障注入转换为可重复执行、可生成脱敏证据的检查，而不是依赖人工观察容器列表。

### 测试先行

为 `scripts/verify_deployment.py` 增加单元测试，使用假命令执行器验证：

- 任一关键命令失败时总体失败；
- 报告记录命令名、退出码、耗时和截断输出；
- 输出自动删除 URL 中的密码、Token、Key、Cookie 和宿主机绝对路径；
- 八库状态、迁移 revision、readiness、bootstrap 幂等和恢复结果均为必填证据；
- 没有真实 LLM Key 时只跳过 LLM 冒烟，不把阶段整体伪报为全部完成；最终关闭阶段 3 前仍要求用户完成一次真实 `/query` 冒烟。

### 实现

1. 新增 `scripts/verify_deployment.py`，支持：
   - Compose 静态校验；
   - 镜像构建；
   - 启动与 `--wait`；
   - migrate/bootstrap 退出状态；
   - readiness；
   - Alembic head；
   - 八库状态；
   - 检索冒烟；
   - 文档任务冒烟；
   - bootstrap 二次执行；
   - 重启恢复；
   - 可控故障注入；
   - JSON/Markdown 脱敏报告。
2. 所有 Docker 命令都要求显式 project name `lexrag-stage3-acceptance`，禁止使用默认项目名。
3. 清理命令只允许删除该 project 的容器和 volume；执行前列出并校验资源前缀。
4. 报告默认写入 `reports/deployment/`，只提交聚合后的非敏感报告，不提交完整日志。

### 专用冷启动命令

用户最终在 PowerShell 中执行，示例：

```powershell
Copy-Item .env.docker.example .env.docker.stage3
# 手工填写 .env.docker.stage3 中的随机 JWT、MySQL 密码和 BGE-M3 宿主机路径

$env:COMPOSE_PROJECT_NAME = 'lexrag-stage3-acceptance'
docker compose --env-file .env.docker.stage3 config --quiet
docker compose --env-file .env.docker.stage3 build
docker compose --env-file .env.docker.stage3 up -d --wait
python scripts\verify_deployment.py --project-name lexrag-stage3-acceptance --env-file .env.docker.stage3
```

若需要重新做真正空卷验收，只能针对已经确认名称前缀为 `lexrag-stage3-acceptance` 的专用项目执行：

```powershell
docker compose --project-name lexrag-stage3-acceptance --env-file .env.docker.stage3 down --volumes
```

不得对默认 project、未知 volume 或现有 LexRAG 开发环境使用 `down --volumes`。

### 提交

```text
test(stage-3): automate cold-start deployment evidence
```

## Task 9：完整回归与真实验收

### 自动化门禁

先执行 Stage 3 聚焦测试，再执行完整质量门禁：

```powershell
python -m pytest tests\test_deployment_settings.py tests\test_alembic_contract.py tests\test_embedding_contract.py tests\test_statute_catalog.py tests\test_deployment_bootstrap.py tests\test_readiness.py tests\test_compose_contract.py tests\test_nginx_contract.py -q
python scripts\quality_gate.py
git diff --check
git status --short
```

记录实际通过数、覆盖率、警告和耗时；不得预先写死为当前的 300 项。

### 冷启动验收矩阵

| 场景 | 预期结果 |
|---|---|
| 全新专用 volume | migrate、bootstrap、API、Worker、Vue 全部完成并 ready |
| 八库校验 | 全部 READY；计数、hash、fingerprint 与 manifest 一致 |
| 重复 bootstrap | 全部 skipped 或 no-change，不产生重复数据 |
| API/Worker 重启 | 数据保留，readiness 自动恢复 |
| MySQL/Redis 重启 | 依赖恢复前 not-ready，恢复后 ready |
| 缺失模型挂载 | bootstrap/ready 明确失败，不转用远程 API |
| 维度或 fingerprint 冲突 | 拒绝 collection，不继续读写 |
| 构建中断 | 旧 READY collection 和 DB 指针不变 |
| 真实检索 | 无 LLM Key 也能完成法规浏览/检索冒烟 |
| 真实 `/query` | 用户通过前端内存配置运行时 LLM Key 后完成一条问答冒烟 |
| 文档上传 | 真实 Worker 将仓库样本文档处理到 READY |

真实 `/query` 只证明部署链路通，不评价回答的法律正确性。

## Task 10：文档、证据与阶段关闭

### 实现

1. 新增 `docs/deployment.md`：
   - 前置环境；
   - `.env.docker` 配置；
   - BGE-M3 挂载；
   - 启动、查看状态、日志、停止；
   - migrate/bootstrap 单独重跑；
   - Windows 本地 Worker `--pool=solo`；
   - 备份和恢复说明；
   - 安全清理专用验收 project。
2. 更新 README 快速开始、架构图、健康端点和部署边界。
3. 更新 `.env.example`，删除 SQLite/PostgreSQL 过时注释；新增 `.env.docker.example`。
4. 更新 `docs/status/feature-ledger.md` 的部署状态和证据路径。
5. 写入 `docs/status/stage-3-deployment-verification.md`，引用机器可读报告并记录实际结果。
6. 只有完整验收通过后，更新外部 `E:\个人发展\002职业\项目1：RAG法律\RAG法律.md`：
   - 阶段 3 标为完成；
   - 总体关闭阶段从 3/9 更新为 4/9；
   - 写入实际提交、测试数、冷启动环境和证据路径；
   - 保留“非生产可用、非法律效果结论”的边界。

### 文档真实性检查

搜索并处理当前状态中的过时表述：

```powershell
rg -n "docker-compose\.v3|docker-compose\.yml|Streamlit|SQLite|PostgreSQL|create_all|E:/huggingface/model|initializing|Docker 冷启动.*待" README.md docs config.py Dockerfile compose.yaml .env.example
```

历史设计文档中的旧描述保持历史事实，不为追求搜索结果为零而改写历史记录。

### 最终提交

```text
docs(stage-3): record reproducible deployment verification
```

## 最终审查清单

- [ ] `git status --short` 仅包含本阶段预期文件。
- [ ] 没有真实密码、API Key、JWT、Cookie、MCP Token 或私有咨询内容。
- [ ] 没有修改正式/临时评测问题、标签和历史结果。
- [ ] 没有直接连接或清理用户现有数据库和 volume。
- [ ] 单一 Compose 是唯一当前部署入口。
- [ ] 空 MySQL 只通过 Alembic 完成 schema 创建。
- [ ] API 启动不执行 `create_all()`、seed 或索引重建。
- [ ] Embedding 无静默回退，collection 身份可验证。
- [ ] 八库 bootstrap 幂等且失败不破坏旧 READY 数据。
- [ ] readiness 对关键依赖失败返回 503。
- [ ] Worker 健康检查证明 broker 和节点可达。
- [ ] Nginx `/api` rewrite 与前端契约一致。
- [ ] 冷启动、重复初始化、重启恢复和故障注入均有脱敏证据。
- [ ] 完整后端、前端、Ruff、类型检查和构建通过。
- [ ] 阶段 3 文档没有夸大为生产可用或法律效果完成。

## 实施完成后的交付形式

最终向用户交付：

1. 变更摘要与提交列表；
2. 新的部署架构和关键设计解释；
3. 用户可亲自执行的 PowerShell 冷启动与复验命令；
4. 实际自动化结果和真实 Docker 验收证据；
5. 未完成项或环境阻塞，如实保留，不通过改文档或改数据制造完成状态。

