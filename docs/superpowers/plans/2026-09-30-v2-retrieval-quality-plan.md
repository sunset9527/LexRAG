# LexRAG v2.0 实施计划

> 基于 `2026-09-30-v2-retrieval-quality-design.md`。所有代码变更遵循 Red → Green → Refactor：先新增最小失败测试、确认因缺失功能而失败，再编写最小生产代码。

## 0. 基线与边界

- 不改动用户已有的未跟踪评测脚本或 `frontend/tsconfig.tsbuildinfo`。
- PDF/Word 模块只保留其“代码、自动化和 DOCX 端到端验收已完成；本机全服务人工验收未完成”的事实边界。
- 每次评测输出包含样本数、评测集版本和逐题排名；没有真实人工标注的数据不生成宣传指标。

## 1. 检索评测数据契约与指标运行器

**测试先行**

1. 新建 `tests/test_retrieval_evaluation.py`：校验 JSONL 必填字段、空/重复相关条文、未知知识库和无候选的失败路径。
2. 以确定的假检索结果测试 Recall@K、MRR、NDCG@K 的数值与逐题报告；测试运行器遇到无效样本返回非零失败。
3. 先运行该测试，确认失败原因是模块不存在。

**最小实现**

1. 新建 `src/evaluation/retrieval_evaluation.py`：定义标注加载、检索结果归一化、指标计算与 JSON 报告写入。
2. 新建 `scripts/evaluate_retrieval.py`：只接受已存在的 JSONL 数据集、知识库 slug 和 K 值；在真实 Chroma 上调用指定库检索器。
3. 新建带字段说明的 `data/evaluation/README.md` 和最小人工标注数据文件。迁移现有 15 条前先逐条核验其相关法条；未核验样本不会进入正式数据集。

**验证**：目标测试通过；对真实人工标注集运行脚本时生成可审计 JSON 报告。

## 2. 多候选 Query Rewrite 与 HyDE 融合检索

**测试先行**

1. 新建 `tests/test_query_expansion_retriever.py`，验证：原问题始终参与召回；重复或空候选会去重；HyDE 仅作为召回文本；改写或 HyDE 报错时仅使用原问题并报告降级原因。
2. 用假底层检索器的固定结果验证多路 RRF 会按 `article_id` 去重、保留来源查询，并保持确定排序。
3. 为 `QueryRewriter` 新增失败测试：合法 JSON 中的候选数组被规范化为最多 3 条；旧的单条响应继续兼容。
4. 先确认这些测试因候选接口和融合检索器不存在而失败。

**最小实现**

1. 扩展 `src/retrieval/query_rewriter.py` 的结果模型与 prompt，使其能返回最多 3 个候选；保留单候选兼容和原问题回退。
2. 新建 `src/retrieval/query_expansion_retriever.py`，包装 `LawRetriever`：对原问题、候选与 HyDE 各自 `retrieve()`，以 RRF 合并为 `RetrievalResult`，并透传精确条文查询方法给自校验。
3. 修改 `src/agent/workflow.py`，在每个请求的运行时 LLM 配置生效后构造包装检索器，交由 Agent 工具注册；修复当前仅计算 `enhanced_query` 却未影响检索的缺口。
4. 调整 `src/agent/tools.py` 仅经该包装检索器搜索；在工具输出和 `QueryResult.metadata` 写入增强状态、候选数量与回退原因，不暴露 HyDE 文本为法条引用。

**验证**：新增离线测试通过；既有 `tests/test_retrieval_optimizer.py`、`tests/test_retrieval_expansion.py` 继续通过；评测运行器在同一真实标注集上给出前后可比较报告。

## 3. Redis 查询缓存

**测试先行**

1. 新建 `tests/test_query_cache.py`：精确命中不执行底层查询；不同用户、知识库、模型、Base URL、Prompt/检索版本绝不共享键；TTL 固定为 3600 秒。
2. 测试语义命中严格限定在同一作用域、阈值大于 0.9，metadata 含原问题和相似度。
3. 测试 Redis 客户端异常时缓存层旁路且查询仍成功；异常结果不写缓存。
4. 先运行并确认因缓存服务不存在而失败。

**最小实现**

1. 将 `redis` 声明为显式运行依赖；在 `config.py` 增加 Redis URL、TTL、语义阈值和可追踪的检索配置版本。
2. 新建 `app/services/query_cache_service.py`：封装精确键、作用域、序列化、语义候选索引和容错旁路；不存 API Key。
3. 修改 `api.py` 的 `/query`：在创建请求级工作流前查询缓存，成功响应后才写缓存；将 `exact`/`semantic`/`miss` 信息放入响应 metadata。
4. 修改 `frontend/src/api/query.ts` 和 `frontend/src/stores/chat.ts` 保存缓存 metadata；在 `frontend/src/views/Chat.vue` 为语义命中显示清晰提示。

**验证**：缓存服务/API 测试通过，Redis 关闭的测试仍通过；前端类型检查和构建通过。

## 4. 真实用户收藏

**测试先行**

1. 新建 `tests/test_favorite_service.py`：收藏保存问题、答案、引用、知识库、领域和当前用户；重复请求幂等或返回冲突（按 API 契约确定）；删除不会影响其他用户。
2. 新建 `tests/test_favorite_api.py`：未登录返回 401，列表只能看本人，领域/知识库过滤正确，非法收藏 ID 返回 404。
3. 先运行并确认因模型、服务和路由不存在而失败。

**最小实现**

1. 新建 `app/models/favorite.py`，并创建对应 Alembic revision（若项目缺少既有 revision，则在文档中说明并使用项目当前 `Base.metadata` 初始化策略后补齐迁移链）。字段遵循设计文档；唯一性基于 `user_id` 与答案指纹。
2. 新建 `app/services/favorite_service.py` 和 `app/api/favorites.py`；复用 `get_current_user`，不接受请求体中的 `user_id`。
3. 修改 `api.py` 的 `/query` 使用真实 JWT 用户而非固定 `user_id=1` 记录聊天历史，并把可收藏的完整快照返回给前端。同步评估该变更对未认证 API 使用者的兼容策略，并以契约测试固定。
4. 新建 `frontend/src/api/favorites.ts`、`frontend/src/views/Favorites.vue`，在 `router/index.ts` 与 `components/AppLayout.vue` 注册入口；在 Chat 的助手消息上提供收藏/取消收藏。

**验证**：服务/API 授权测试、前端类型检查和生产构建通过；不同 JWT 用户的隔离由 API 测试覆盖。

## 5. 模型配置校验、集成验证与文档

**测试先行**

1. 为 `api.py` 的运行时请求头增加契约测试：非法 Base URL/模型名返回 422；无 Key 的非 LLM 数据接口仍可用；LLM 路径的降级或错误明确可见。
2. 为查询 API 增加端到端假组件测试：缓存命中、增强回退、真实用户聊天历史与收藏可共同工作。

**最小实现与核验**

1. 抽取请求配置解析与基本格式校验，保证日志中不出现 API Key 或完整敏感问题。
2. 运行新增测试、所有既有 `tests/`、真实人工标注评测脚本，以及 `frontend/npm run build`。
3. 仅在上述结果真实通过后更新 README、`RAG法律.md` 和迭代记录；明确报告评测样本数、实际指标、缓存/收藏边界和未完成的文档人工部署验收。
