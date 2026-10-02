# LexRAG v3.0 实施计划：本机可演示企业级平台

**依据：** `docs/superpowers/specs/2026-10-02-v30-enterprise-platform-design.md`  
**开发原则：** 每项生产行为执行 Red → Green → Refactor；测试必须先以预期原因失败。不得触碰工作区内不属于 v3.0 的未提交改动。

## Phase 0：基线、边界与迁移

1. 运行 `alembic heads`，以实际 head 写入下一迁移的 `down_revision`；当前已知 head 是 `20261001_03`，但不以此替代现场确认。
2. 运行现有认证、会话、知识库、场景、文档和查询测试，记录基线；历史失败必须先定位，不能归因给 v3.0。
3. 新增 v3.0 模块限定在 `app/models`、`app/services`、`app/api`、`app/tasks`、`frontend/src`、`infra`、`tests` 与部署文档；不改写证据工作流和引用校验语义。

## Phase 1：组织 RBAC 与数据迁移

### Red

新建 `tests/test_rbac_service.py`，用 SQLite 和两个组织、三类角色验证：

- 活动组织必须存在且用户确实属于该组织；伪造组织不能构造上下文。
- `admin` 拥有预期权限，`lawyer`/`member` 不拥有管理权限。
- 角色变更后新请求即时生效，不读取 JWT 中的旧权限。
- 跨组织资源过滤为空；具体资源按服务约定返回“未找到”。
- 演示组织迁移逻辑幂等，不重复创建成员或角色。

单独运行，确认失败因为 RBAC 模型/服务不存在。

### Green

1. 新建 `organization.py`、`rbac.py` 模型，包含组织、角色、权限、角色权限和用户角色及必要唯一索引。
2. 新建 `authorization_service.py`：种子化固定权限矩阵、构造 `AuthorizationContext`、验证组织成员、检查权限。
3. 扩展 `User` 与可隔离资源的模型，添加可空的迁移字段并将已有数据回填到“本机演示组织”；新写入在服务层要求组织和创建者。
4. 创建 Alembic 迁移，升级顺序为创建 RBAC → 创建演示组织/角色 → 回填 → 添加索引；降级以可安全撤销的结构操作为限。
5. 注册模型，重跑 Phase 1 测试及现有会话/收藏/场景服务测试。

## Phase 2：授权依赖、成员与组织 API

### Red

新增 `tests/test_rbac_api.py`，依赖覆盖验证：

- `X-Organization-ID` 缺失、非法、非成员均被拒绝。
- 管理端点从 JWT 用户和活动组织构造上下文，不接收客户端传入的 user ID/role。
- 无权限管理操作为 403；跨组织对象为 404。
- 创建、列举、禁用成员只影响当前组织。

### Green

1. 新建 FastAPI `get_authorization_context` 和 `require_permission` 依赖。
2. 新建 `app/api/admin.py` 与 `organization_service.py`，实现当前组织、成员列表、角色授予/撤销和成员启停的最小契约。
3. 将会话、收藏、场景、文档和知识库路由逐步接收上下文；先维持默认演示组织的向后兼容，再用服务层组织过滤收紧读写。
4. 每一类资源补充一条跨组织契约测试，避免仅覆盖新 API。

## Phase 3：审计、Agent 配置与管理统计

### Red

新增 `tests/test_audit_service.py`、`tests/test_usage_service.py`：

- 审计事件只能创建和查询，模型/服务不存在 update/delete 通道。
- 审计 metadata 会移除 API Key、JWT、password、question/answer 原文。
- 查询审计保留内容哈希、长度、校验状态和追踪 ID。
- 同一请求追踪 ID 的日统计重复投递不重复累计。
- 管理员可以按组织/日期读取统计，非管理员不能读取。

### Green

1. 新增 `AuditLog`、`UsageDaily`、`AgentConfig` 模型和迁移。
2. 新增审计服务（白名单 metadata 和 SHA-256 摘要）及使用统计服务（按事件 ID 幂等聚合）。
3. 在管理写操作、`/query`、外部源检查和 MCP 调用的规范入口写审计；不能记录密钥或回答原文。
4. Agent 配置服务只接受白名单字段并验证范围；新增管理 API 和权限测试。
5. 新增管理员仪表板 API，返回聚合值而非用户问题明细。

## Phase 4：管理后台

### Red

1. 先为管理员 API 增加完整后端契约测试。
2. 在 `frontend/src` 定义严格的 API 类型、权限判定纯函数和路由 meta；运行 `npm run build`，确认新增页面引用在未实现前产生预期类型/模块错误。

### Green

1. 新建 `AdminLayout.vue`、Dashboard、成员、知识库授权、Prompt、Agent、审计、统计、法规订阅页面及 API 客户端。
2. 管理菜单和 `/admin` 路由仅对管理员显示；路由守卫拒绝非管理员，但不替代后端控制。
3. 将现有 Settings 的 Prompt 入口改为受 `prompts:manage` 保护的管理页；保持 Prompt 版本历史。
4. 用 `npm run build` 验证严格 TypeScript 与生产构建。

## Phase 5：MCP 与外部来源适配

### Red

新建 `tests/test_mcp_tools.py`、`tests/test_external_legal_source.py`：

- MCP 工具只能读当前组织授权资源；未授权/跨组织结果不可见且会写审计。
- Wikipedia 返回 URL 和非权威来源标识。
- 国家法律法规库/裁判文书网来源未配置、超时、非 2xx 或访问拒绝都返回结构化降级，绝不返回伪造结论。
- HTTP MCP 配置只允许 loopback、Origin 校验和 Bearer Token；stdio 没有额外 stdout 日志污染协议。

### Green

1. 抽取共享的法律只读服务门面，REST 与 MCP 均使用它来做授权、审计与结果序列化。
2. 新建 MCP server、stdio 入口、HTTP 入口和五个只读工具。
3. 实现 `ExternalLegalSource` 协议、MediaWiki 适配器和两种默认禁用的中国法律来源适配器。
4. 用 httpx mock 验证外部边界；不在测试或生产中绕过来源访问限制。

## Phase 6：法规订阅、更新差异与任务

### Red

新增 `tests/test_law_update_service.py`：

- 同一来源哈希重复检查不重复创建事件或通知。
- 变化生成 `PENDING_REVIEW`，只读快照可追溯来源与时间。
- 仅管理员确认后创建版本链并投递重建；任务失败不改变 READY 知识库。
- 无权限用户不能订阅、确认或读取其他组织事件。

### Green

1. 新增订阅、来源快照、更新事件、通知和法规版本模型/迁移。
2. 实现来源检查、哈希比较、条文级 diff、确认和幂等任务服务。
3. 新增 Celery 更新任务与 Beat 调度；调度频率由环境变量设置。
4. 增加管理 API/前端订阅页面，显示来源、更新时间、差异和确认状态。

## Phase 7：监控与 Docker 全栈

### Red

1. 新增指标测试：`/metrics` 可抓取、业务指标不含敏感/高基数标签、查询/任务的计数与时延在测试调用后变化。
2. 为 Compose 增加配置验证和冷启动冒烟脚本：服务清单、私有端口、健康检查、Nginx `/api` 不 rewrite、seed 无数据时失败。

### Green

1. 用 Prometheus Python client 暴露 API/业务自定义指标，worker/beat 写入受控计数与耗时。
2. 添加 `infra/prometheus`、`infra/grafana` 预置数据源和演示 Dashboard。
3. 新建 v3 Compose 覆盖文件或独立本机演示 Compose，含 nginx、mysql、redis、api、worker、beat、prometheus、grafana、mcp、seed；使用独立命名 volume 和仅 loopback 端口。
4. Nginx 提供 Vue 构建产物且 `/api` 原样代理；不暴露 MySQL/Redis/API 容器端口。
5. 文档说明启动、停止、日志、数据卷与 MCP stdio 调用方式。

## Phase 8：回归与真实验收

1. 跑完整后端 pytest、Ruff、前端 build 和 Compose 配置检查。
2. 本机演示验收：管理员创建组织成员与角色；律师/普通用户验证隔离；审计/统计可查；MCP 能安全检索；法规更新用本地可追溯 fixture 触发“发现→确认→版本链”；Grafana 展示指标。
3. 记录可复现的命令、样本来源、实际结果和失败降级。未做人审的法律回答质量不写性能结论。
4. 仅提交 v3.0 文件；不夹带已有 v2.3/v2.4 未提交改动。
