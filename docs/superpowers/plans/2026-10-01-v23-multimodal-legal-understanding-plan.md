# LexRAG v2.3 实施计划：多模态法律理解

**状态：** 已完成设计，待开始 v2.3.1 实现

**依据：** `docs/superpowers/specs/2026-10-01-v23-multimodal-legal-understanding-design.md`
**开发原则：** 每个生产行为严格遵循 Red → Green → Refactor。先写最小失败测试并实际确认失败原因，再写最小实现；不得以测试后补代替测试先行。

## 当前事实与不可破坏约束

- 已有主链为 `DocumentIngestionService -> DocumentJob -> Celery process_document_task -> DocumentProcessingService -> DocumentIndexer`。不得新建第二套上传、队列或向量入库链路。
- `src/ingestion/pdf_parser.py` 已使用 PyMuPDF 文本层和 RapidOCR 回退；v2.3.1 扩展其结果，不替换其本地优先原则。
- 现有数据库迁移 head 是 `20261001_01_add_scenario_jobs.py`；创建新 revision 前必须再次运行 `alembic heads`，并从实际 head 填写 `down_revision`，不能假定 revision ID。
- `DocumentIngestionService._serialize()` 当前将内部 `storage_path` 返回给 API；v2.3 应移除该泄露字段。Worker 仍从 ORM 对象读取该字段，不受影响。
- 当前文档 API 没有 JWT 用户鉴权；本版本只做文档与文档库归属校验，不把用户隔离误写为已完成。RBAC 留待 v3.0。
- 现有工作树有与 v2.1/v2.2 相关的未提交改动；本计划只新增或修改下列 v2.3 文件，不暂存、格式化或回滚其他改动。

## Phase 0：建立 v2.3.1 回归基线

1. 运行现有文档链路测试：
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_document_parser.py tests/test_document_ingestion_service.py -q
   ```
2. 记录当前结果；若它们失败，先按 `systematic-debugging` 的定位流程修复或与用户确认，不能把历史失败归因于 v2.3。
3. 运行 `alembic heads`、`alembic current`，记录实际迁移状态；如果现有 scenario migration 尚未应用，迁移验收必须在独立开发库或由用户确认的本机库执行，不能修改生产数据。
4. 为新增样本建立 `tests/fixtures/v23/`：
   - 一份含重复页眉页脚和简单矢量表格的原生 PDF；
   - 一份由测试注入 OCR 结果模拟的扫描页输入；
   - 一份编号合同文本；
   - 一份最小判决书文本。
   测试生成的小型 PDF 只含自编内容，不使用真实当事人信息或未经授权的裁判文书。

## Phase 1：v2.3.1 页面级持久化与迁移

### 先写失败测试

1. 新建 `tests/test_document_analysis_models.py`：验证一个 `DocumentJob` 能关联多个有唯一 `(document_id, page_number)` 的页面；结构化结果一文档一条；关系边必须具备起点、关系类型、建立方式和至少一种证据（法条号、相似度或证据文本）。
2. 运行该测试，确认失败原因是 `DocumentPage`、`DocumentStructure`、`DocumentRelation` 尚不存在，而非测试配置错误。
3. 新建 `tests/test_document_result_service.py`：验证结果序列化不包含 `storage_path`，页面查询按页分页并只返回请求文档，结构化结果的字段保留页码和证据片段。
4. 运行该测试，确认失败原因是结果服务/API 契约尚不存在。

### 最小实现

1. 新建模型文件：
   - `app/models/document_page.py`：`document_id` 外键、`page_number`、原始/检索文本、`source`、`ocr_confidence`、JSON 表格、页眉、页脚和 JSON 警告；对 `(document_id, page_number)` 建唯一约束。
   - `app/models/document_structure.py`：`document_id` 唯一外键、`document_type`、`content_json`、`parser_version`、`status`、`error_message`、时间戳。
   - `app/models/document_relation.py`：源文档/定位符、目标类型/ID、关系类型、可选法条号/相似度、证据文本、建立方式和引擎版本；模型校验保证至少一个证据字段非空。
2. 在所有创建 `Base.metadata` 的测试导入路径中注册这三个模型；生产应用也必须在 `init_db()` 之前导入它们。
3. 新建 Alembic revision，例如 `alembic/versions/<new_revision>_add_document_analysis.py`：从实际 head 接续，创建三表、外键、唯一约束及 `document_id`/查询用索引；`downgrade()` 按依赖的反向顺序删除。
4. 调整 `DocumentIngestionService._serialize()`，去掉 `storage_path`；现有上传测试改为通过会话读取 `DocumentJob.storage_path` 断言文件已保存，而不是把内部路径当 API 输出。
5. 新建 `app/services/document_result_service.py`：只读地提供文档概要、分页页面和关系序列化；查询时验证 `DocumentJob` 存在且与请求的文档库一致。
6. 再运行 Phase 1 测试与既有上传测试，确认全部通过后再做命名、重复查询等小幅重构。

## Phase 2：v2.3.1 丰富解析器、OCR 元数据、页眉页脚与表格

### 先写失败测试

1. 新建 `tests/test_rich_document_parser.py`，用真实小型原生 PDF 验证：
   - 文本层页面标记 `source="text"`，不会调用 OCR 注入器；
   - 扫描页使用注入的 OCR 适配器，并保存文本、来源、平均置信度或“不可用”；
   - 连续页重复的顶部/底部短行被标记为页眉/页脚，且 `search_text` 不含这些内容；
   - `Page.find_tables()` 找到的矢量表格保存页码、边界、行列矩阵和 `method="pymupdf"`。
2. 单独运行测试，确认失败原因是丰富解析器还不存在；OCR 适配器可使用测试替身，因为真实 OCR 模型是外部重量级依赖，测试目标是调用边界和元数据保存，不是模型识别能力。
3. 扩展 `tests/test_document_parser.py`，断言旧的 `parse_document()` 仍返回可分块的 `text/page/paragraph` 兼容结构。

### 最小实现

1. 新建 `src/ingestion/rich_document_parser.py`，定义小型数据契约（dataclass 或 TypedDict）：`ParsedPage`、`ExtractedTable`、`ParsedDocument`。契约必须区分：原始页面文本、去噪后检索文本、表格、来源、页码、OCR 信号和警告。
2. 在 `src/ingestion/pdf_parser.py` 提取可注入的 OCR 适配层：保留原 `_ocr_page()` 的兼容返回，新增返回文本与可用置信度的内部函数；模型加载和异常策略继续延迟加载、不因单页异常终止文档。
3. `rich_document_parser` 对 PDF 使用既有 PyMuPDF：先取文本层，低于当前阈值时使用 OCR，再调用 `Page.find_tables()` 提取原生矢量表格。该 API 已由 PyMuPDF 官方 `Page` 文档列出，项目当前依赖 `PyMuPDF>=1.24.0`，因此不引入 Camelot、Tabula-Java 或额外系统依赖。
4. 在完整页面列表生成后，以归一化文本、重复页数和顶部/底部位置识别候选页眉页脚。原始文本保留，`search_text` 排除它们；不根据一次出现的行删除正文。
5. 对 DOCX 生成同一丰富契约：段落与表格行保留为页面为空的来源片段，标注 `source="docx"`，避免伪造页码。
6. 让 `src/ingestion/document_parser.py` 保持旧接口，并从丰富结果投影到既有列表；这样既有调用方和测试可无破坏迁移。
7. 运行新旧解析器测试；通过后检查格式与 Ruff。

## Phase 3：v2.3.1 接入 Worker、索引与只读详情 API

### 先写失败测试

1. 扩展 `tests/test_document_ingestion_service.py`：以真实数据库会话和注入的丰富解析结果验证 Worker 会持久化页面、写入去噪后的 `parsed_text`、只对 `search_text` 分块、在表格/OCR 子步骤有警告时仍能 `READY`。
2. 新建或扩展 API 契约测试，验证：
   - `GET /documents/{id}/result` 返回统计、结构化占位和来源而不返回 `storage_path`；
   - `GET /documents/{id}/pages?page=1&page_size=...` 返回稳定排序和边界校验；
   - 不存在文档返回 404，文档与给定库不匹配返回 422/404（按现有 API 错误风格统一）。
3. 运行测试，确认失败原因是 Worker 仍调用旧解析器、路由尚未注册。

### 最小实现

1. 将 `DocumentProcessingService` 的解析依赖升级为返回丰富契约的注入点，默认使用 `parse_document_details()`；保留兼容适配器供已有单元测试和迁移期调用。
2. 在 `PARSING` 开始后持久化 `DocumentPage`；构造 `parsed_text` 与传给 `DocumentChunker` 的 segments 时仅使用 `search_text`，并让 chunk metadata 保留 `document_id`、页码、段落和可选表格定位符。
3. 将子进度与解析警告写进已有可序列化结果（不增加新的顶层任务状态）；若全部页面都没有可索引文本，调用已有 `mark_failed()`；否则完成原有 CHUNKING/INDEXING/READY 路径。
4. 在 `api.py` 的 lifespan 组件中注册 `DocumentResultService`，实现三个只读端点：`/documents/{id}/result`、`/documents/{id}/pages`、`/documents/{id}/relations`。本阶段 relations 为空列表而不是伪造关系。
5. 更新 `frontend/src/api/documents.ts` 的类型和调用函数，但不在此阶段改大面积 UI。
6. 运行相关 pytest、全量后端回归及前端类型检查，记录真实结果。

## Phase 4：v2.3.1 前端详情与可解释状态

1. 先在 `frontend/src/api/documents.ts` 添加失败的类型检查所需类型与请求函数，再运行前端检查确认类型/调用尚未接入。
2. 修改 `frontend/src/views/Documents.vue`：
   - 保留单文件上传、轮询和重试；
   - 点击任务打开详情抽屉或详情区；
   - 显示页面、来源、OCR 警告、表格摘要和分页；
   - 明确标识 OCR/低置信度信息，不将其标为法律结论。
3. 对 `PARSING` 展示可解释的子阶段文案，而不显示 Prompt、思维链、内部文件路径或密钥。
4. 运行 `npm run build`；手工用小型自编 PDF 验证文本页、扫描页和表格页的状态、详情和重试。
5. v2.3.1 仅在自动化、前端构建和真实小样本验收均完成后，才更新 README 与路线图状态；未做人工复核的指标保持为空。

## Phase 5：v2.3.2 合同与判决书结构化

### 先写失败测试

1. 新建 `tests/test_contract_structure_parser.py`：验证 `第一条`、`第 X 条`、`1.1` 编号能切出范围，并只从对应原文填充当事人、标的、价款、履行、违约、免责、争议解决、管辖、期限；缺少证据时值为 `null`/“未识别”。
2. 新建 `tests/test_judgment_structure_parser.py`：针对自编最小文书验证当事人、案由、诉请、事实、法院认为、裁判结果、引用法条均附页码与 `evidence_text`。
3. 新建 `tests/test_document_structure_service.py`：验证类型不确定为 `general`、LLM 适配器故障时规则结果仍保存、任何没有原文回指的 LLM 字段被拒绝。
4. 分别运行并确认失败，再开始实现。

### 最小实现

1. 新建 `src/ingestion/legal_document_structure.py`：包含文档类型路由、合同解析器和判决书解析器；所有输出采用 Phase 1 的字段证据 JSON 契约。
2. 正则和段落锚点负责主路径；LLM 补充封装为可选、一次调用、可注入的适配器。它必须返回候选值及原文定位，服务层逐项验证定位存在才落库。
3. 新建 `app/services/document_structure_service.py`，在 Worker 的页面持久化后、普通分块前执行；解析异常写 `DocumentStructure.status="FAILED"` 与错误信息，但不阻塞通用文本入库。
4. 在结果 API 与文档详情中展示 `document_type`、字段、方法、页码和证据片段；结构化失败或 general 文档显示明确降级提示。
5. 对固定小样本做人工逐字段回指复核，只报告样本数与真实的字段可回指率，不能用模型自评替代。

## Phase 6：v2.3.3 跨文档关联与批量处理

### 先写失败测试

1. 新建 `tests/test_document_relation_service.py`：验证法条编号精确匹配、同一文档库内语义候选、合同条款到已验证法规证据三类边；验证跨库候选被拒绝、相同边幂等去重、没有证据字段的边拒绝持久化。
2. 新建 `tests/test_document_batch_service.py` 和 API 契约测试：验证一批文件逐一建任务/投递，重复或格式非法的单文件返回独立错误而不回滚合格文件。
3. 运行测试，确认失败原因分别为关联与批量接口未实现。

### 最小实现

1. 新建 `app/services/document_relation_service.py`：先实现确定性法条编号匹配；语义候选通过显式注入的检索器获得，限制为同一文档库；合同到法规边必须引用已有的、同库作用域验证通过的证据。
2. 自动关联运行在文档 `READY` 后的独立 Celery 任务或同一任务的受控末段；关联失败仅记录警告，不把已索引文档改为 FAILED。
3. 在 `DocumentIngestionService` 新增批量提交方法；在 `api.py` 新增 `POST /document-libraries/{slug}/documents/batch`，使用 `list[UploadFile]` 和逐文件临时落盘/清理，复用单文件校验和派发。
4. 修改 `frontend/src/api/documents.ts` 与 `frontend/src/views/Documents.vue` 支持多选、逐文件队列结果、关联候选和统计；相似度边明确标为“相关候选，非法律结论”。
5. 运行新测试、全量 pytest、前端生产构建；用一组自编批量材料验证独立成功/失败与关联证据展示。

## Phase 7：最终验收、文档与提交边界

1. 执行：
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   cd frontend
   npm run build
   ```
2. 在本机 MySQL、Redis、Celery、API 和 Vue 均已启动时，对不含敏感信息、可复核的小样本文档进行真实端到端验收。记录：样本组成、OCR 字符错误（如人工有标注）、字段可回指率、表格可用率、关联人工确认率、失败/降级数量和耗时。
3. 任一指标缺少人工标注时标为空并解释；不编造准确率、法律效果或规模数据。
4. 仅将本计划新增的 v2.3 文件按逻辑拆分提交；不夹带现有未提交文件。实际完成的范围才更新 `README.md` 和 `E:\个人发展\002职业\项目1：RAG法律\RAG法律.md`。

## 计划自检

- 每一阶段都列出先失败的测试、最小实现、回归范围和降级行为。
- 没有新增云端 OCR、用户级鉴权、裁判文书抓取或第二套队列。
- 表格方案使用现有 PyMuPDF 的 `Page.find_tables()`，避免新增 Camelot/Tabula 的系统依赖。
- 权限现状、内部路径泄露、未提交工作树与人工指标边界均已明确。

## 规划记录

| 事项 | 处理结果 |
| --- | --- |
| 计划技能模板要求根目录 `task_plan.md` / `findings.md` / `progress.md` | 这些文件已在工作树中未跟踪，归属不明；为保护用户/既有迭代内容，未覆盖，改在 `docs/superpowers/plans/` 写入本版本独立、可提交的计划。 |
| 初次读取网页工具结果的对象结构与预期不同 | 未重试同一调用；改为直接打开 PyMuPDF 官方 Page 文档，确认 `find_tables()` 可用。 |
