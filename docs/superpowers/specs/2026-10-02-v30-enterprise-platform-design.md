# LexRAG v3.0：本机可演示的企业级平台设计

## 目标与边界

v3.0 将现有 LexRAG 升级为可在本机 Docker 环境完整演示的法律 AI 平台。交付 RBAC、组织级数据隔离、管理后台、审计日志、使用统计、MCP、法规订阅更新、Prometheus/Grafana 与全栈 Compose。

本期不承诺公网生产部署、SSO、邮件/短信通知、或绕过第三方网站限制抓取数据。所有法律结论继续受现有证据账本和引用校验约束。

## 架构决策

采用模块化单体，不拆分微服务。FastAPI、Vue、MySQL、Redis、Celery 和 Chroma 已在项目中使用；v3.0 在此基础上增加边界清晰的模型、服务、API 路由和管理界面。业务规则只放在服务层，REST API 与 MCP 共用同一授权、审计和检索入口。

不采用“前端隐藏菜单”作为权限控制，也不让 MCP 直连数据库绕过权限。每个受保护操作均在后端验证当前用户、当前组织和权限。

## 一、组织、角色与行级隔离

### 数据模型

新增：

- `organizations`：组织名称、状态、创建时间。
- `roles`：`admin`、`lawyer`、`member` 三个组织内角色。
- `permissions`：稳定的动作代码，例如 `members:manage`、`knowledge_bases:manage`、`prompts:manage`、`agents:manage`、`audit:read`、`analytics:read`、`law_updates:manage`。
- `role_permissions`：角色与权限的关系。
- `user_roles`：用户、组织、角色；同一用户可以加入多个组织。

现有 `User.is_superuser` 保留为本机初始系统管理员的引导能力，不作为普通业务授权的依据。启动迁移创建“本机演示组织”，把现有用户和现有业务数据归属其中。

会话、收藏、场景任务、文档任务、知识库及新增 v3.0 业务记录都有 `organization_id` 和 `created_by`。官方法规等可显式标记为系统共享资源；组织资源默认不跨组织可见。

### 授权流程

客户端每次请求选择活动组织。服务端从 `X-Organization-ID` 读取候选组织，验证用户成员资格后构造 `AuthorizationContext`。JWT 只用于认证，不缓存角色；角色变更立即在下一次请求生效。

`require_permission(code)` 是所有管理操作的 FastAPI 依赖。业务服务接收 `AuthorizationContext`，按组织和创建者过滤；无权访问另一组织的具体资源时返回 404，缺少动作权限时返回 403。Celery 任务只接收资源 ID 与提交者 ID，执行时重新读取并验证归属。

权限矩阵：

| 能力 | admin | lawyer | member |
|---|---|---|---|
| 管理成员、角色、组织配置 | 是 | 否 | 否 |
| 管理组织知识库、Prompt、Agent | 是 | 否 | 否 |
| 查询组织获授权知识库 | 是 | 是 | 是 |
| 查看组织共享业务数据 | 是 | 是 | 否 |
| 查看/修改自己业务数据 | 是 | 是 | 是 |
| 审计与统计 | 是 | 否 | 否 |

## 二、管理后台、审计与统计

`/admin` 使用独立 Vue 布局，路由守卫只改善体验；数据 API 仍以后端授权为准。页面包括总览、成员与角色、知识库授权、Prompt 版本、Agent 配置、审计日志、使用统计与法规订阅。

`agent_configs` 仅允许白名单参数：案例/图谱检索开关、Top-K、超时、模型别名和版本说明。不执行管理页面输入的任意 Python、Shell 或工具代码。

`audit_logs` 为仅追加记录：组织、操作者、动作、目标类型和 ID、结果、请求追踪 ID、时间与最小必要元数据。`/query` 记录问题与回答的 SHA-256、长度、知识库、引用校验结果和耗时；不在审计表重复保存问题、回答或 API Key 原文。所有写入、授权拒绝、管理操作、MCP 调用和法规更新确认均生成审计记录。

`usage_daily` 以组织和日期聚合查询量、成功/失败、缓存命中、延迟、估算 token、法律领域及日活用户数。管理图表读取该表。Prometheus 只承担系统运行指标，不携带 user ID、question、session ID 或 answer 等高基数/敏感标签。

## 三、MCP 与外部法律来源

MCP 为只读工具集，至少提供：

- `search_local_statutes`：在当前组织授权的本地法规知识库检索。
- `get_law_article`：读取当前组织可见的法条详情。
- `search_cases`：检索当前组织可见案例。
- `search_wikipedia_legal_concept`：通过官方 MediaWiki REST API 查询法律概念，返回来源链接并标明它不是法律权威来源。
- `get_law_update_status`：读取法规订阅、上次检查和待确认变更。

MCP 支持 stdio 和 Streamable HTTP。stdio 用 Compose 的一次性 `mcp` 服务启动；HTTP 仅绑定 `127.0.0.1`，校验 Origin 并要求 Bearer Token。两种传输都构造同样的 `AuthorizationContext` 并写入同一审计表。

国家法律法规数据库与中国裁判文书网实现 `ExternalLegalSource` 适配器。适配器只有在来源 URL、访问策略和允许用途明确配置后才发起读取；没有稳定授权接口或出现反爬/访问失败时，返回明确的不可用状态、来源和失败原因。不得把失败或页面摘要伪装为检索结果或法律结论。

## 四、法规更新与版本链

`law_subscriptions` 保存组织、法规名称、关联知识库、配置来源和关注状态。`law_source_snapshots` 保存可追溯来源 URL、获取时间、版本提示、内容摘要和哈希；`law_update_events` 保存检测出的变化、状态和确认者。

Celery Beat 周期投递检查任务。任务用条件请求或来源允许的方式读取元数据；相同哈希不生成重复事件。变化事件生成条文级差异，状态为 `PENDING_REVIEW`。只有管理员确认后才创建新版本、触发索引重建并保留旧版本；失败不会覆盖当前 READY 知识库。通知首先为站内未读通知，邮件/短信留到后续版本。

## 五、本机 Docker 拓扑

默认 Compose 启动 `nginx`、`api`、`worker`、`beat`、`mysql`、`redis`、`prometheus`、`grafana` 和 HTTP MCP 服务。Nginx 托管 Vue 生产构建，并将 `/api` 原样代理到 API。业务服务位于私有网络；宿主机只绑定：应用 `127.0.0.1:8080`、Grafana `127.0.0.1:3000`、Prometheus `127.0.0.1:9090` 和 MCP HTTP `127.0.0.1:8001`。

MySQL、Redis、Chroma、上传原件、法规版本和 Grafana 使用独立命名 volume。v3.0 的本机演示使用新 volume，不连接或覆盖当前 Windows MySQL 数据库。一次性 `seed` 服务只导入仓库内可追溯且已校验的数据；找不到可用数据时失败并给出导入提示，绝不生成虚构法条。

Prometheus 抓取 API `/metrics` 及 worker/beat 自定义指标；Grafana 预置本地演示仪表盘。服务均有健康检查，API 依赖 MySQL/Redis 就绪，worker/beat 不作为 API 对外可用性的前置条件。

## 错误处理与安全基线

- 组织缺失、伪造或无成员资格：403；跨组织资源：404；缺少操作权限：403。
- 审计写入异常不泄露业务内容；高风险管理写操作优先失败并返回可诊断错误。
- 外部来源、Redis、Prometheus 或 Grafana 不可用不得阻断法律问答；外部工具响应包含降级原因。
- 不在日志、审计、指标、缓存作用域或错误响应写入 API Key、JWT、原始密码。
- 所有回答继续显示法律信息免责声明；法规更新未经人工确认不得成为检索依据。

## 测试与验收

实现严格采用测试先行。每个新增生产行为均先有可解释的失败测试。

1. 角色权限矩阵、活动组织校验、跨组织资源不可见、Celery 再校验。
2. 管理 API 的 403/404 契约、Agent 参数白名单、审计不可篡改及敏感字段不落审计。
3. 日聚合幂等、指标不含敏感/高基数标签、管理统计正确隔离。
4. MCP 的授权、stdio/HTTP 安全配置、工具来源声明和外部连接器故障降级。
5. 更新任务的哈希幂等、待审查差异、确认后版本链与索引、失败不破坏 READY 库。
6. 后端完整 pytest、前端 production build、Compose 冷启动、登录/切换组织/管理操作/MCP 查询/法规更新模拟的端到端冒烟。

## 非目标

- 公网域名、TLS 证书、OAuth/SSO、邮件短信、Kubernetes 和多节点高可用。
- 对没有公开授权接口的第三方网站进行绕过限制的抓取。
- 将统计、监控、页面展示或自动化测试结果表述为法律意见或真实法律效果。
