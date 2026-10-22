# LexRAG 阶段 3：可复现部署与运行时基础设施收口设计

**状态：** 已获用户确认，待实施计划与代码执行  
**日期：** 2026-10-22  
**基线：** `abcb569`（Stage 2 已关闭）

## 1. 目标

将 LexRAG 从“已有容器配置但不能证明冷启动后可查询”收口为可复现的本机全栈部署：在全新、独立的数据卷上，通过一套明确命令完成数据库迁移、八部法规初始化、运行时服务启动和健康检查，最终得到能够登录、浏览法规、检索和处理文档的 LexRAG。

阶段 3 只证明部署、恢复和运行时基础设施可复现，不提前宣称法律回答准确、生产可用或完成阶段 4—8 的质量目标。

## 2. 已确认的设计决策

### 2.1 采用单一编排入口

仓库最终只保留一个权威 `compose.yaml`。现有 `docker-compose.yml` 和 `docker-compose.v3.yml` 的有效配置合并后退出当前部署入口，避免数据库、端口、数据卷和启动命令存在两套事实口径。

默认拓扑包含：

- MySQL；
- Redis；
- 一次性 `migrate` 服务；
- 一次性 `bootstrap` 服务；
- FastAPI API；
- Celery Worker；
- Celery Beat；
- Vue/Nginx；
- Prometheus；
- Grafana。

MCP stdio 和 HTTP 服务继续作为可选 profile，不阻塞默认启动。

### 2.2 迁移、初始化和服务启动分离

部署依赖链固定为：

```text
MySQL / Redis healthy
        ↓
migrate: alembic upgrade head
        ↓
bootstrap: 基础数据 + 八部法规 + Chroma + 图谱
        ↓
API / Worker / Beat
        ↓
Vue/Nginx + Prometheus/Grafana
```

三类动作由不同命令承担：

- `migrate` 只执行数据库迁移；
- `bootstrap` 只执行幂等基础数据和知识库初始化；
- API 启动只建立连接和装配运行时组件，不建表、不重建索引。

Compose 可以把三个动作编排成一次启动，但代码边界必须保持分离。

### 2.3 MySQL 是唯一正式数据库口径

阶段 3 的开发说明、Compose 和正式部署统一使用 MySQL。删除“SQLite/PostgreSQL 自动切换”等已经不符合代码现状的描述，并移除未被运行时代码使用的 PostgreSQL/pgvector 依赖。

测试仍可在适合的单元测试中使用 SQLite，但不得将其描述为 LexRAG 的部署数据库。

### 2.4 本地 BGE-M3 是正式验收路径

Embedding 由显式配置选择：

- `EMBEDDING_PROVIDER=local`：加载只读挂载到容器内固定路径的 BGE-M3；
- `EMBEDDING_PROVIDER=zhipu`：显式配置智谱 Embedding 服务。

不再允许“本地模型失败后静默切换远程 API”。缺少所选 provider 的必要配置时，bootstrap 和严格运行模式必须失败并指出缺少的配置项，但不得输出凭据值。

本阶段的正式 Docker 冷启动验收使用本地 BGE-M3。远程模式只验证配置和适配器契约，不以外部付费调用作为阶段关闭条件。

## 3. 当前断点

阶段 3 实施前存在以下已核实问题：

1. 两份 Compose 对 MySQL、端口、数据卷和启动流程的定义不一致。
2. `requirements.txt` 缺少 Compose URL 所需的 `PyMySQL`，且文档解析依赖重复、核心依赖仅使用宽泛下界。
3. `init_db()` 在 API 启动时执行 `Base.metadata.create_all()`。
4. Alembic 首个迁移引用 `users.id`，但迁移链没有负责创建历史基础表的基线迁移，空 MySQL 无法可靠从零升级。
5. 默认 Embedding 路径是 Windows 宿主机路径，容器没有对应挂载。
6. Embedding provider 会静默回退，collection 没有可验证的模型和维度身份。
7. `/health` 只检查进程内组件字典，初始化状态仍返回 HTTP 200。
8. Dockerfile 保留缺失 `main.py` 的 Streamlit target 和旧架构说明。
9. 七部法规与民法典使用不同脚本；部分资料准备逻辑依赖宿主机绝对路径。
10. API 启动混合数据库建表、Prompt seed、Embedding 加载和业务组件初始化，失败后可能继续存活并被误判为健康。

## 4. 运行时与依赖设计

### 4.1 版本口径

实施时以 Stage 2 已通过的 Python 3.13 环境为起点，先在 Linux 容器内验证 BGE-M3、PyTorch、ONNX Runtime、Chroma、LangChain/LangGraph 和文档解析依赖的兼容性，再冻结确切补丁版本。若某个原生依赖在 Python 3.13 容器中不能可靠安装，只允许整体回退到一个经过完整验证的 Python 版本，不允许本机、CI 和 Docker 各自使用不同主次版本。

Node 同样统一到一个经过前端构建验证的 LTS 版本。Dockerfile、README 和实际质量门禁必须引用相同版本。

Python 依赖采用：

- 直接依赖清单；
- 与目标 Python/容器平台对应的精确 constraints/lock；
- Docker 和部署验证使用同一锁定结果。

前端以已有 `package-lock.json` 为唯一锁文件，Docker 和 CI 均使用 `npm ci`。

基础镜像固定到补丁版本；冷启动验收后在部署报告中记录实际镜像 digest。

### 4.2 数据库账号

MySQL root 账号只用于容器初始化和管理，不作为 API 运行账号。API、Worker、Beat、migrate 和 bootstrap 使用独立 `lexrag` 应用账号。

Compose 必须显式要求：

- MySQL root 密码；
- MySQL 应用账号密码；
- JWT 密钥。

这些值只来自运行环境或未入库的 env 文件，不写入镜像、仓库、日志或健康响应。

## 5. Alembic 与数据库启动设计

### 5.1 连接初始化

`app/db/session.py` 的职责收缩为：

- 构造 SQLAlchemy Engine；
- 构造 Session factory；
- 提供请求级 session。

`init_db()` 不再导入全部模型并执行 `Base.metadata.create_all()`。测试中若需要 `create_all()`，继续由测试夹具显式执行。

### 5.2 基线迁移

新增一个真正的 Alembic 基线 revision，创建 2026-10-01 迁移链之前已经存在的基础表、索引、唯一约束和外键。现有根迁移改为依赖该基线 revision。

兼容策略如下：

- 空 MySQL：从基线 revision 开始完整执行至唯一 head；
- 已在当前 head 的开发库：新基线被纳入 revision 祖先关系，但不得重复创建现有表；
- 旧开发库：只在复制出来的临时数据库中演练升级，不直接对用户现有库做破坏性试验；
- 迁移失败：输出失败 revision 和恢复说明，不自动执行危险 downgrade。

模型元数据与迁移最终状态要通过 schema 比对测试，避免迁移完成后仍与 ORM 模型漂移。

## 6. Embedding 与索引身份设计

### 6.1 显式 provider

Embedding 工厂根据配置创建唯一 provider，不做隐式回退。缓存键至少包含 provider、模型标识和运行设备，避免测试或多配置进程错误复用全局实例。

本地模式启动前验证：

- 模型目录存在且只读可访问；
- 必要模型文件存在；
- 能生成测试向量；
- 实际向量维度等于配置维度。

### 6.2 Embedding fingerprint

fingerprint 由以下稳定信息构成：

- provider；
- 模型标识或本地模型版本标识；
- 输出维度；
- normalize 设置；
- 索引格式版本。

知识库注册和 Chroma collection 元数据均保存：

- 法规清洗文本 SHA-256；
- Embedding fingerprint；
- 索引格式版本；
- 构建时间和文档/chunk 数。

读取现有 collection 时，模型维度或 fingerprint 不匹配必须返回结构化失败，禁止继续读写。

## 7. 八部法规与幂等 bootstrap

### 7.1 单一法规目录

建立一个共享的八部法规目录定义，统一描述：

- slug；
- 法律名称；
-领域；
- 清洗文本路径；
- 来源 manifest 项；
- 预期首末条号和法条数；
- 清洗文本 SHA-256。

民法典不再由独立、不可组合的初始化路径管理。现有七部法规脚本、民法典脚本和 bootstrap 共同复用该目录，不复制定义。

阶段 3 不修改法规文本、权威来源断言和有效性结论。法规权威性、时效性及版本链属于阶段 4。

### 7.2 初始化事务边界

bootstrap 对每个法规库执行：

1. 校验本地清洗文本与 manifest 哈希；
2. 计算目标 source hash 和 Embedding fingerprint；
3. 若 DB 指针、collection 元数据和计数完全匹配，则标记为 skipped；
4. 否则构建隔离的新 collection；
5. 校验解析法条数、chunk 数、向量维度、metadata 和抽样检索；
6. 校验成功后，在数据库事务内切换活动 collection 指针并标记 READY；
7. 失败时保留旧指针和旧 READY collection，新 collection 记录为失败或待清理工件。

幂等性以内容和模型身份为依据，不以“同名 collection 已存在”作为成功条件。

### 7.3 基础数据和派生结构

bootstrap 还负责：

- 创建默认组织、角色、权限和 Prompt 模板；
- 按显式环境变量幂等创建管理员；
- 重建或验证法规知识图谱；
- 为 API 启动时的 BM25 内存索引提供可验证的活动 collection 数据。

服务启动不重复执行以上工作。

## 8. Compose、镜像和数据卷设计

### 8.1 一次性任务

`migrate` 和 `bootstrap` 为一次性服务。API 只在两者成功退出后启动；Worker 和 Beat 至少依赖 migrate 成功，并使用与 API 完全相同的数据、模型和连接配置。

### 8.2 只读与可写数据分离

镜像内的已跟踪法规清洗文本是只读 seed 输入。运行时数据使用独立路径和 volume：

- MySQL；
- Redis；
- Chroma；
- 用户上传；
- 法规更新快照；
- 图谱运行产物；
- Grafana。

不得把命名 volume 挂载到整个 `/app/data` 并遮蔽镜像中的法规源文件。

本地 BGE-M3 以只读 bind mount 挂载到固定容器路径。Compose 在挂载缺失时不得悄悄下载或切换 provider。

### 8.3 端口和网络

宿主机默认只绑定：

- LexRAG Web；
- Grafana；
- Prometheus；
- 用户显式启用时的 MCP HTTP。

MySQL、Redis 和 API 只存在于 Compose 私有网络。API 调试端口若需要暴露，使用单独的开发 override，而不是默认配置。

## 9. 健康检查设计

### 9.1 API 健康端点

提供：

- `/health/live`：进程事件循环可响应即返回 200；
- `/health/ready`：关键依赖全部满足才返回 200，否则返回 503；
- `/health`：作为兼容入口，使用 readiness 语义。

readiness 至少检查：

- 数据库连接；
- Alembic revision 等于唯一 head；
- Redis 可达；
- Embedding provider 可用且实际维度正确；
- 图谱可加载；
- 八部法规知识库处于 READY；
- 每个活动 collection 存在；
- source hash、Embedding fingerprint 和计数匹配。

响应只暴露组件名、状态、稳定错误码和必要的非敏感计数，不输出数据库 URL、文件绝对路径、凭据或底层异常文本。

### 9.2 Worker 与外围服务

Worker 健康检查必须证明 Celery 节点能够通过 broker 响应，而不是仅检查进程存在。Windows 本地文档继续明确 `--pool=solo`；Docker/Linux 使用容器支持的 worker 配置。

Prometheus、Grafana 和外部 LLM 不属于 API readiness 的硬依赖。Redis 在本阶段按路线图要求属于 readiness 硬依赖，即使部分查询缓存代码可以旁路 Redis。

## 10. Nginx 设计

Nginx 保持前端现有契约：浏览器请求 `/api/...`，代理时移除 `/api` 前缀并转发到当前 FastAPI 根路由。不得误改为保留前缀。

同时配置：

- 与 FastAPI/Celery 一致的上传上限；
- 连接、发送和读取超时；
- 安全响应头；
- gzip；
- 带内容哈希静态资源的长期缓存；
- 为未来 SSE 准备的代理缓冲关闭配置。

本阶段不实现阶段 6 的 HTTP 流式接口。

## 11. 测试与真实验收

### 11.1 自动化测试

新增或扩展以下契约：

- 空库迁移到 head；
- 历史 schema 副本升级；
- ORM metadata 与迁移 schema 一致；
- development/demo/production 配置边界；
- 必填密钥缺失时安全失败；
- Embedding provider 不回退；
- fingerprint 和维度不匹配阻断；
- 八库 bootstrap 成功、跳过、失败隔离和原子切换；
- liveness/readiness 状态码和故障矩阵；
- Compose 服务清单、依赖、端口、volume 和健康检查；
- Nginx `/api` rewrite 和上传约束；
- Worker broker 健康；
- 现有完整后端回归、Ruff、前端 Node 契约、类型检查和生产构建。

### 11.2 冷启动验收

正式关闭阶段 3 前，必须在专用的全新 Compose project 和空 volume 上完成：

1. 构建全部镜像并启动默认拓扑；
2. `migrate` 和 `bootstrap` 成功结束；
3. readiness 返回 200；
4. Alembic 位于唯一 head；
5. 八个法规库全部 READY，法条数、chunk 数、哈希和 fingerprint 可核验；
6. 可登录、浏览法规并完成不依赖 LLM 的真实检索；
7. 用户配置有效运行时 LLM Key 后完成一条 `/query` 冒烟请求；
8. 上传一个仓库内非敏感样本文档，真实 Worker 将其处理到 READY；
9. 再次执行 bootstrap，证明没有重复 collection 或计数增长；
10. 重启 API、Worker、MySQL 和 Redis，证明数据保留且 readiness 恢复；
11. 模拟 Redis 断开、缺失模型、维度冲突、空 collection 和 bootstrap 中断，证明 not-ready、失败提示和旧 READY collection 保护符合设计。

真实验收使用独立 volume，不覆盖用户现有 Windows MySQL、Chroma 或上传数据。

## 12. 验收证据与文档

新增脱敏的 Stage 3 部署验证报告，记录：

- Git 提交；
- 操作系统与 Docker/Compose 版本；
- Python、Node、MySQL、Redis 和关键镜像版本/digest；
- 实际执行命令及退出码；
- 迁移 revision；
- 八库的非敏感计数、哈希和 fingerprint 摘要；
- bootstrap 首次与重复执行结果；
- 重启恢复和故障注入结果；
- 后端、前端和静态检查的实际通过数及警告。

报告不得包含 API Key、密码、JWT、咨询原文、上传正文、私有文件路径或完整异常内容。

README、部署环境模板、功能台账和外部 `RAG法律.md` 只在相应事实通过验证后更新。若冷启动未通过，阶段 3 继续标记为进行中，并列出真实阻塞，不用静态配置检查替代真实验收。

## 13. 明确不在本阶段实施

- 法规权威来源接入、有效期、司法解释和版本时间线；
- 自动选库和跨库证据编排；
- HTTP SSE/流式回答；
- 正式法律效果评测或人工逐条法律结论审核；
- CI 工作流的最终合并治理；
- 公网生产部署、TLS、Kubernetes、微服务拆分；
- 新 Agent、新页面、新模型提供商或检索算法调整。

## 14. 完成定义

阶段 3 只有在以下条件全部满足时才能标记 100%：

- 单一 Compose 是唯一部署事实源；
- 空 MySQL 能只通过 Alembic 建成完整 schema；
- API 启动不执行 `create_all()` 或数据重建；
- 本地 BGE-M3 挂载、维度和 fingerprint 可验证；
- 八部法规 bootstrap 幂等且失败时不破坏旧 READY 数据；
- liveness/readiness 不再产生假健康；
- Worker、数据卷、重启恢复和空卷初始化经过真实 Docker 验收；
- 完整代码质量回归通过并留下脱敏证据；
- 文档只陈述已验证事实，不宣称生产可用或法律效果完成。

