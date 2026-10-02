# LexRAG v2.4 实施计划：会话记忆与个性化

**状态：** 已规划，尚未开始实现  
**依据：** `docs/superpowers/specs/2026-10-01-v24-session-memory-design.md`  
**开发原则：** 每项生产行为严格执行 Red → Green → Refactor：先写最小失败测试并实际确认失败原因，再写最小实现。禁止为通过测试而放宽用户隔离或证据校验。

## 当前事实与不可破坏约束

- `src/workflow/legal_evidence_workflow.py` 是固定 Python 调用链，不是 LangGraph `StateGraph`；v2.4 不引入 PostgreSQL、`PostgresSaver` 或工作流重写。
- 现有 `chat_history` 已保存问答，但 `/query` 写死 `user_id=1`，且 `query_id` 可能不是稳定会话 ID；必须改为真实 JWT 用户与显式会话。
- `build_evidence_answer_generator()` 只接收本轮 `evidence`。历史只能作为闭包注入的辅助上下文；`CitationVerifier` 的输入必须继续是本轮 `EvidenceLedger`，不得把历史引用混入。
- 缓存当前在检索前命中即直接返回。v2.4 必须先解析会话、将 `session_id` 纳入作用域，并将命中回答也写入该会话历史；不得因为缓存绕过会话审计或活跃时间更新。
- `favorites`、`scenarios` 已采用 `get_current_user` + 独立服务层的模式；会话 API 必须复用该授权模式。
- 数据库迁移当前已到 `20261001_02`。创建新迁移前必须再次运行 `alembic heads`，用实际 head 填写 `down_revision`，不能假定 ID。
- 工作树可能存在其他版本未提交改动；只修改本计划列出的 v2.4 文件，不格式化、暂存或回滚无关文件。

## Phase 0：回归基线与迁移状态

1. 运行现有相关测试，记录结果：

   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_evidence_workflow.py tests/test_query_cache.py tests/test_favorite_service.py tests/test_favorite_api.py -q
   ```

2. 运行 `alembic heads` 与 `alembic current`，记录真实 revision；若历史测试失败，先定位根因，不能归因给 v2.4。
3. 检查既有 API 路由、模型导入和测试 SQLite 建表方式，确认新模型在生产 `init_db()` 和测试 `Base.metadata.create_all()` 中都被注册。

## Phase 1：会话、画像与服务边界

### 先写失败测试

1. 新建 `tests/test_session_service.py`，使用 SQLite 内存库和两个用户，验证：
   - 创建会话生成 UUID、归属用户、默认活跃状态；首条问题能生成不超过 120 字的标题。
   - 列表只返回当前用户的未归档会话，按 `updated_at` 倒序；标题搜索只匹配当前用户。
   - 读取、重命名、归档均按用户隔离；其他用户得到“未找到”结果，不能探测资源。
   - 归档会话不能接受新轮写入；已有历史仍保留用于审计，但不由活跃列表返回。
   - 最近历史按创建时间升序返回最多五轮；每轮只保留 `is_verified=true` 的引用，未校验引用被滤除。
2. 在同一测试文件中验证 `UserProfile`：仅调用“已校验成功”的更新入口才增加知识库与意图计数；更新失败/未通过回答不能影响计数。
3. 单独运行该测试，确认失败原因是模型与服务不存在，而非缺少用户外键或测试夹具错误。

### 最小实现

1. 新建 `app/models/session.py`：`sessions` 表含 UUID `id`、`user_id`、`title`、`created_at`、`updated_at`、`is_active`，及 `(user_id, is_active, updated_at)` 索引。
2. 新建 `app/models/user_profile.py`：`user_profiles` 表含 `user_id` 主键/外键、`law_area_counts` JSON、`intent_counts` JSON、`updated_at`；JSON 的空值默认安全为空对象。
3. 在 `ChatHistory` 增加会话关系（或明确的外键迁移），同时保持既有行可迁移：先为已有合法 `session_id` 建回填会话，再在数据库层加外键约束；如果当前库无法安全回填，则迁移只增加索引、由服务层强制新写入一致性，并在迁移说明记录此限制。
4. 在 `app/db/session.py:init_db()` 注册两种新模型；添加 Alembic revision，按实际 head 创建表、索引及安全的升级/降级顺序。
5. 新建 `app/services/session_service.py`，让其独占会话创建、列出、搜索、历史读取、重命名、归档、活跃检查、写入一轮历史和画像增量更新。用事务确保“写历史 + 更新时间 + 已通过时画像更新”原子完成。
6. 不在服务层接收客户端 `user_id` 以外的会话归属参数；用户 ID 仅由路由的 JWT 依赖提供。
7. 重跑 Phase 1 测试并执行受影响模型/收藏回归；通过后只重构重复序列化和标题截断逻辑。

## Phase 2：受保护的会话与推荐 API

### 先写失败测试

1. 新建 `tests/test_session_api.py`，仿照 `test_favorite_api.py` 用 FastAPI、依赖覆盖和假服务验证：
   - 路由从 `get_current_user` 取用户，而不是接收请求中的 `user_id`。
   - `POST /sessions`、`GET /sessions?q=`、`GET /sessions/{id}`、`PATCH /sessions/{id}`、`DELETE /sessions/{id}` 都将登录用户 ID 传给服务层。
   - 服务层返回找不到时，读取/重命名/归档统一为 404，不泄露他人会话存在性。
   - `GET /recommendations` 不接收任意用户 ID，且返回推荐理由字段 `based_on_law_area`。
2. 运行测试，确认失败来自尚未注册的会话路由。

### 最小实现

1. 新建 `app/api/sessions.py`：定义最小请求/响应 Pydantic 模型和上述六个端点；使用 `get_current_user`、`db_session.SessionLocal` 与 `SessionService`。
2. 推荐规则放在 `SessionService.get_recommendations()`：读取画像中最高计数的、仍为 `READY` 的知识库；返回法规浏览、案例检索和预设常见问题入口。无有效画像时返回民法典通用入口。
3. 在 `api.py` 注册新 router；不向推荐响应中写入模型猜测、案情判断或“适用法律结论”。
4. 运行 API 契约测试及 Phase 1 服务测试。

## Phase 3：受控记忆注入与缓存隔离

### 先写失败测试

1. 新建 `tests/test_conversation_memory.py`，直接测试回答生成器的 Prompt 构造：
   - 最近五轮中，问题、回答与已校验法条可作为“历史上下文”出现。
   - 第六轮及更早记录不出现；未校验引用不出现。
   - Prompt 明确历史不构成新证据，且新结论只能引用本轮提供的证据。
   - 不传历史时保持 v2.1 的回答生成行为。
2. 扩展 `tests/test_evidence_workflow.py`：让生成器带入一条历史法条、但本轮账本只有另一条；验证历史法条引用仍被 `CitationVerifier` 拒绝。这是防止“记忆绕过证据门控”的关键回归测试。
3. 扩展 `tests/test_query_cache.py`：相同问题、相同用户和模型但不同 `session_id` 必须产生不同精确与语义作用域；同一会话仍可命中。
4. 分别运行，确认失败是记忆/会话缓存尚未接入。

### 最小实现

1. 在 `app/services/session_service.py` 定义小型、脱敏的 `ConversationTurn` 数据契约和 `format_memory_context()`：最多五轮，每段对问题/回答设定固定字符上限，仅输出经验证的引用 ID；避免将内部 metadata、Token、Prompt、API Key 或 JWT 写入上下文。
2. 将 `build_evidence_answer_generator(llm)` 扩展为可选的 `memory_context` 参数。闭包在本轮证据段之前加入标记清晰的历史段，并写明历史只能用于代词/话题理解，不能作为法律结论或引用来源。
3. 不修改 `LegalEvidenceWorkflow` 的 `answer_generator(question, evidence, issues)` 契约：每个请求创建的生成器闭包绑定自己的历史，避免并发串话。
4. 将 `session_id` 加入 `cache_scope`；缓存键保持不保存 API Key/JWT 原文。更新缓存版本字符串以避免旧作用域与新作用域混用。
5. 重跑本阶段测试、`test_evidence_workflow.py` 和 `test_query_cache.py`。

## Phase 4：/query 接入真实用户、稳定会话与统一落库

### 先写失败测试

1. 新建 `tests/test_query_session_integration.py`，以注入的会话服务、缓存服务和最小工作流替身覆盖：
   - 未传 `session_id` 时为当前用户创建会话，响应 `query_id` 等于该会话 ID；传入会话时验证归属与活跃状态。
   - 归档、未知、他人会话都被拒绝为 404，且不会触发 LLM/检索/缓存读取。
   - 查询历史写入真实登录用户而不是用户 1；成功后更新会话时间和标题。
   - 精确缓存和语义缓存命中也会创建一条该用户、该会话的问答审计记录并更新时间；缓存内容本身不含跨会话历史。
   - 仅 `verification_status="pass"` 的新回答更新画像；失败结果仍记录问答但不更新画像、不写缓存。
   - 响应 metadata 的 `memory_turns_used` 等于实际用于 Prompt 的轮数，不回显历史文本。
2. 运行测试，确认失败来自 `/query` 仍使用匿名 `user_scope`、随机 thread ID、早返回缓存和硬编码用户。

### 最小实现

1. 在 `/query` 添加 `current_user: User = Depends(get_current_user)`；前端已有 Axios JWT 注入，不新增 Token 存储方案。
2. 在任何缓存读取、检索或 LLM 调用之前，通过 `SessionService` 解析或创建会话，读取受控历史并固定 `query_id=session.id`。
3. 缓存命中不直接 `return`：统一转换为结果载荷后进入“持久化问答 → 更新时间 → 按校验状态更新画像 → 响应”路径。缓存服务故障继续按现有设计旁路。
4. 工作流生成器以该请求的 `memory_context` 构造；把 `memory_turns_used` 放入返回 metadata。保持本轮 `EvidenceLedger`、引用校验、一次受控修复及失败不缓存的既有语义。
5. 删除 `/query` 内直接 `SessionLocal` + `ChatHistory(user_id=1, ...)` 的重复写库块，所有持久化收敛到 `SessionService`。
6. 运行 Phase 4 测试与全部查询缓存/证据工作流回归。

## Phase 5：Vue 会话管理、历史恢复与推荐入口

### 先写失败检查

1. 在 `frontend/src/api/` 增加会话和推荐 TypeScript 契约；先让 `vue-tsc -b` 因 Store/View 尚未接入而暴露类型缺口，避免依赖 `any` 掩盖 API 字段错误。
2. 为 Store 提取可测试的纯函数（消息映射、会话排序、标题截断）并新增最小测试；若仓库尚未配置前端测试运行器，不临时加入测试框架，改以严格类型检查与后端 API 契约覆盖，并在执行记录说明该限制。

### 最小实现

1. 新建 `frontend/src/api/sessions.ts`：封装会话创建、列表、详情、重命名、归档和推荐请求；类型包含消息、校验状态、会话时间、推荐理由与入口。
2. 重构 `frontend/src/stores/chat.ts`：会话列表仅来自服务端；实现加载列表、加载详情、创建会话、重命名、归档和发送完成后的局部更新。刷新时可恢复历史，不再把内存数组当数据源。
3. 修改 `frontend/src/views/Chat.vue` 为三栏：
   - 左栏为搜索框、创建按钮、会话列表、重命名和归档操作；
   - 中栏复用现有消息、证据工作流和收藏 UI；
   - 右栏继续为法条溯源，底部显示可解释推荐入口。
4. 监听 `/chat/:sessionId`：会话选择后更新路由并加载详情；创建会话回到 `/chat`，首问成功后替换为实际 `/chat/{sessionId}`。无权、归档或不存在时显示可操作提示并回到新会话。
5. 对历史消息按后端返回的校验状态渲染，不凭前端推断引用“已验证”。网络失败不清空已经加载的消息。
6. 运行：

   ```powershell
   cd frontend
   npm run build
   ```

## Phase 6：最终回归、真实验收与文档

1. 执行后端全量回归与前端构建：

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   cd frontend
   npm run build
   ```

2. 在用户自己的本机 MySQL、Redis、API 与 Vue 服务均启动后，用两个测试账号完成真实验收：
   - 账号 A 创建两个会话、连续追问、刷新后恢复，并确认只有最近五轮进入下一轮上下文；
   - 账号 B 不能读取、搜索、改名、归档或继续 A 的会话；
   - 将某会话归档后验证无法继续提问；
   - 验证缓存同会话可命中、跨会话不复用；
   - 检查推荐响应含基于真实领域统计的理由，且未包装为法律结论。
3. 记录真实样本、用户隔离、引用校验状态、缓存命中、端到端延迟和异常降级结果。没有人工标注时，不宣称会话记忆提升法律准确率或推荐命中率。
4. 仅在自动化、前端构建和真实验收完成后，更新 `README.md`、路线图 `E:\个人发展\002职业\项目1：RAG法律\RAG法律.md` 与版本状态；只提交本版本文件，不夹带已有未提交改动。

## 计划自检

- 每个阶段先写可观察的失败测试，再实施最小代码并做受影响回归。
- 没有引入第二套数据库、LangGraph 重写、云端记忆服务或不透明的 LLM 推荐。
- 会话隔离覆盖 API、服务、缓存和前端加载四层；所有资源不属于当前用户时统一 404。
- 历史不会混入证据账本；新回答仍只能通过本轮证据与引用校验。
- 缓存命中不再跳过会话审计；失败/无证据结果不污染画像和缓存。
