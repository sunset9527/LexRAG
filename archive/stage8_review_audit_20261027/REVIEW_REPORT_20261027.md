# Stage 8 审核报告（2026-10-27）

审核对象：`review_queue_300.jsonl`（300 条候选：100 条 legacy seed + 200 条 hard candidate）
审核人：高志远　审核时间：2026-10-27T20:30:00+08:00（全部条目同一批次）
落盘文件：`review_queue_300.jsonl`（已填审核字段，`verified_record` 保持 `null`）
原始 pending 备份：`review_queue_300.pending.bak.jsonl`

## 一、审核结论总览

| review_state | 条数 | 说明 |
|---|---|---|
| approved | 109 | 问题与候选法条一致，可直接进入 materialize 流程 |
| revised | 61 | 候选法条/题型/知识库范围需修正后可用 |
| rejected | 130 | 事实不足或题面不成立，不能稳定标注法条 |
| 合计 | 300 | |

按来源与题型拆分：

| origin | proposed_question_type | approved | revised | rejected | 小计 |
|---|---|---|---|---|---|
| legacy_seed | baseline_direct_lookup | 99 | 1 | 0 | 100 |
| hard_candidate | oral_without_law_name | 0 | 50 | 0 | 50 |
| hard_candidate | adjacent_or_confusable | 0 | 0 | 40 | 40 |
| hard_candidate | cross_law | 0 | 0 | 40 | 40 |
| hard_candidate | multi_hop | 0 | 0 | 30 | 30 |
| hard_candidate | insufficient_facts_abstention | 10 | 10 | 0 | 20 |
| hard_candidate | version_or_time | 0 | 0 | 20 | 20 |

## 二、核验方法（可复现）

1. **法条存在性**：用 8 部法律的本地全文（`data/laws/*.txt`）按行首"第X条"切分建索引，逐条解析 `proposed_relevant_article_ids`，校验"法律名+条号"是否真实存在。
   → 结果：300/300 条候选法条全部存在，无凭空编造的条号。
2. **问题-法条一致性**：把题面中引号内的核心问题与对应法条原文做 2-gram 覆盖率比对，再逐条人工阅读条文原文确认。
   → 结果：legacy 100 条中 99 条一致，1 条错配（见下）；hard 200 条的候选法条均与题面内嵌子问题对应。
3. **题面结构检查**：用正则还原 200 条 hard 候选的生成模板，检查是否构成独立的评测题。

## 三、必须记录的问题（按严重度）

### 1. hard 候选 200 条中 180 条是同一批 100 道题的"换皮"，不构成新题
- `oral_without_law_name` 50 条：题面与 legacy 样本**逐字完全相同**（hard-oral-001 = civil-001 …），既未口语化，也未去掉法律术语/法律名称 → 判 `revised`（改题干后可入库）。
- `adjacent_or_confusable` 40 条：统一模板"在"X"这类情形中，若与相近规则混淆，应重点区分哪些适用条件？"，**未指明相邻规则是谁**，标准答案不唯一 → 判 `rejected`。
- `cross_law` 40 条 / `multi_hop` 30 条：把两条互不相关的问题用"当事人同时遇到…""处理…时同时还需要判断…"硬拼成一句（如"打印遗嘱见证人"+"故意杀人罪"），不存在真实的事实链或推理依赖 → 判 `rejected`。
- `version_or_time` 20 条：题干未给定"行为发生时间"和"修订生效日"，且版本适用规则本身未入库 → 判 `rejected`。
- 结论：hard 200 条中只有 `insufficient_facts_abstention` 20 条是真正新增的独立题。**难题集需要重做**，否则 Stage 8 的"hard"指标衡量的仍是 legacy 那 100 道题。

### 2. 发现 1 条真实标注错误（legacy）
- `civil-027`"买卖合同未约定价款支付时间时，买受人何时应付款？"候选标 `民法典第633条`，但第633条规范的是**出卖人分批交付标的物时的合同解除**，与价款支付时间无关；正确条文为**第628条**（买受人应当按照约定的时间支付价款；未约定时在收到标的物或提取标的物单证的同时支付）→ 判 `revised`。

### 3. 知识库文本版本落后于现行法（已在对应 review_note 留痕）
| 法律 | 知识库文本 | 判定依据 | 现行版本差异 |
|---|---|---|---|
| 民法典 | 1260 条 | 与现行一致 | 无 |
| 刑法 | 452 条 + 之一/之二 | 无"已满十二周岁"条款、无第236条之一、无高空抛物等罪名 → **修正案（九）版本** | 现行为修正案（十二）（2024-03-01 施行） |
| 劳动法 | 107 条 | 与现行一致（2018 修正） | 无 |
| 劳动合同法 | 98 条 | 与现行一致（2012 修正） | 无 |
| 公司法 | 218 条 | 2018 修正版 | 2023 修订版 266 条（2024-07-01 施行），条号整体重排 |
| 商标法 | 73 条 | 与现行一致（2019 修正） | 无 |
| 专利法 | 69 条 | 2008 修正版 | 2020 修正版 82 条（2021-06-01 施行），外观设计专利权期限由 10 年改为 15 年 |
| 著作权法 | 61 条 | 2010 修正版 | 2020 修正版 67 条（2021-06-01 施行），"电影作品"改为"视听作品"、"时事新闻"改为"单纯事实消息" |

受影响并已在 note 中标注的 6 条：`criminal-002`、`patent-005`、`company-004`、`company-006`、`copyright-002`、`copyright-003`。
→ **对外口径**：Stage 8 指标只能表述为"在本项目自建法律知识库（部分法律为旧版文本）上的检索效果"，不能表述为"对现行法的问答准确率"。

### 4. 弃答题知识库范围普遍填错
20 条 `insufficient_facts_abstention` 的 `proposed_knowledge_base_slugs` 全部写成了 `civil-code`，其中 10 条实际属于劳动法/劳动合同法/商标法/专利法/著作权法/公司法/刑法范畴（如"公司说要辞退我"属劳动合同法）→ 判 `revised`，另 10 条（合同无效赔偿、肖像权、借贷举证、交通事故、借用物损坏、诈骗界限、监护人责任、口头合同、诉讼时效）确属民法典 → 判 `approved`。

### 5. 语料来源不是官方文本（materialize 前必须解决）
`data/laws/raw/manifest.json` 显示 8 部法律的原始文件是**出版社电子书（来源记录为 z-library.sk）**，`source_assertion` 字段写的是 `user_confirmed_official`，与实际来源不符。
→ 后续 materialize 到 `stage8_dataset` 时需要真实 `source_url` / `source_version`（国家法律法规数据库 https://flk.npc.gov.cn 页面 URL，且该校验器不接受带 query 的 URL），这一项无法由脚本代填，需人工逐法条核对后录入。

## 四、下一步建议

1. **先处理 approved 109 条**：这些可直接 materialize（补 source_url / source_version / reviewer / reviewed_at 到 14 字段格式），形成 Stage 8 第一批正式样本。
2. **revised 61 条**：oral 50 条改写题干（去掉"民法典""刑法"等法律名，改成当事人口吻），abstain 10 条改 slug，civil-027 改条号为第628条。
3. **rejected 130 条退回重出**：真正的难题应当满足"候选法条在题面中不可直接命中"，例如：
   - 跨法条：劳动合同解除 → 经济补偿（劳动合同法46/47）+ 违法解除赔偿（87），同一事实链上的两个条文；
   - 口语化：只给当事人陈述（"老板说试用期三个月不给交社保"），不给任何法律术语；
   - 版本敏感：题干必须写明行为发生时间（"2023年5月签订的合同…"），并配套版本适用规则（刑法第12条从旧兼从轻、民法典时间效力司法解释）。
4. **换语料**：把公司法/专利法/著作权法/刑法换成官方现行文本重新入库，否则版本类题目无法成立。

---

# Round2 复审（2026-10-27 16:14，171 条）

对象：`round2_candidates_171.jsonl`（origin = `round2_remediation`），来源为 Round1 中 191 条非批准条目（61 revised + 130 rejected）的替换候选，其中 20 条 `version_or_time` 按 `round2_remediation_manifest.json` 的 blocker 说明继续挂起，未进入本轮。
落盘：`round2_candidates_171.jsonl`（已填 5 个审核字段，`verified_record` 保持 `null`）；原始 pending 备份 `round2_candidates_171.pending.bak.jsonl`。

## 一、结论

| review_state | 条数 | 分布 |
|---|---|---|
| approved | 160 | oral 49 + adjacent 40 + cross 40 + multi_hop 30 + correction 1 |
| revised | 11 | abstain 10（locator 空）+ oral 1（条号错配） |
| rejected | 0 | — |

**本轮质量与 Round1 的差距是结构性的**：Round1 的 hard 200 条里 180 条是把 100 道 legacy 题换皮（重复 / 空壳模板 / 硬拼），本轮 171 条全部是重新撰写的独立题，题干为当事人视角的口语陈述，候选法条按真实法律关系成组给出。

## 二、逐类核验记录

1. **法条存在性**：171 条涉及的每一条 `proposed_relevant_article_ids` 都在本地语料中按"法律名+条号"命中，0 条凭空条号、0 条格式异常。
2. **oral_without_law_name（50）**：题干已无法律名称、无"第X条""违约责任"这类术语（如"我今年刚过生日，几岁才算成年人？"），49 条与候选法条一致；1 条错配见下。
3. **adjacent_or_confusable（40）**：三组真实易混规则对——违约金调整 vs 实际损失赔偿（585/584）、违约 vs 不可抗力免责（577/590）、定金罚则 vs 减损义务（586/587、591/584），题干给出了具体事实与混淆点，不再是空壳模板。
4. **cross_law（40）**：全部落在劳动法—劳动合同法的同一解除争议链条上（工时/社保/规章制度 → 违纪认定 → 解除程序 → 补偿或赔偿），法条之间是真实依赖，不是两条无关题的拼接。个别延伸到民法典（法人合并承继 67 条 + 劳动合同法 34/47 条），属真实跨法域。
5. **multi_hop（30）**：统一为"违约事实 → 损失范围（584）→ 减损义务（591）"的三跳链，路径可复现。
6. **abstain（10）**：题干沿用 Round1 中判 revised 的 10 条，`expected_knowledge_base_slugs` 已从统一的 `civil-code` 修正为实际法域（labor-contract-law / labor-law / trademark-law / patent-law / copyright-law / company-law / criminal-law），修正正确。
7. **civil 更正（1）**：`round2-civil-correction-001` 已将 Round1 的 `civil-027` 从第633条改为**第628条**，核对无误。

## 三、仍需处理的问题

1. **10 条 abstain 的 `local_source_locator` 是空字符串**。候选队列的字段校验要求该字段非空（`stage8_review_queue.py` 的 `_validate_proposed_values`），这 10 条已标 `revised` 并给出应填内容（"中华人民共和国民法典：弃答题（事实不足，不定位具体条文）"），需在进入队列前补齐。
2. **`round2-oral-039` 条号错配**：「判了缓刑后，需要遵守哪些条件？」指向刑法第75条（缓刑考验期义务），候选给的是第72条（适用缓刑的条件）。已标 `revised` 并给出两种修法（改条号或改题干）。
3. **`round2-oral-045` 有歧义但可答**：「人在国外做的事，什么情况下也可能被追究？」按刑法第6条第三款（行为或结果一项发生在我国领域内即视为领域内犯罪）成立，判 `approved`，note 已注明若题意仅指中国公民境外犯罪则应补第7条属人管辖。
4. **20 条 version_or_time 仍被 blocker 挂起**（manifest 已记录）：本地语料中刑法/公司法/专利法/著作权法为旧版本，且版本适用规则（刑法第12条从旧兼从轻、民法典时间效力规定）未入库，本类题在换语料前无法成立。

## 四、下一步

1. 补齐 10 条 abstain 的 `local_source_locator` + 修正 `round2-oral-039` → 这 11 条可转 approved。
2. 160 条 approved 具备进入 materialize 的条件，但仍需 `source_url` / `source_version`（官方页面 URL，校验器不接受 query 参数）。
3. 换语料（刑法/公司法/专利法/著作权法 → 官方现行文本）后，才能解锁 20 条 version_or_time，也才能把 Stage 8 的指标表述为"对现行法的问答效果"。

---

## 五、Round2 修订记录（2026-10-27 16:18，11 条 → 全部 approved）

上一节标记为 revised 的 11 条已修订完毕，`round2_candidates_171.jsonl` 现为 **171/171 approved**。

| # | queue_id | 修订内容 |
|---|---|---|
| 1 | round2-oral-039 | `proposed_relevant_article_ids` 与 `local_source_locator` 由「刑法第72条」改为**「刑法第75条」**。第75条规定被宣告缓刑的犯罪分子应遵守的四项要求（遵守法律法规并服从监督、报告活动情况、遵守会客规定、离开居住地或迁居需批准），与题干「判了缓刑后需要遵守哪些条件」一致；第72条规定的是可以宣告缓刑的适用条件。 |
| 2-11 | round2-abstain-001 ~ 010 | `local_source_locator` 由空字符串补齐为「<对应法律全称>：弃答题（事实不足，不定位具体条文）」，法律名称与各自的 `proposed_knowledge_base_slugs` 一一对应（劳动合同法 3 条、劳动法 1 条、商标法 1 条、专利法 1 条、著作权法 2 条、公司法 1 条、刑法 1 条）。 |

修订后校验结果：
- 171 行、queue_id 唯一、`review_state` 全部 `approved`、`verified_record` 全部 `null`
- `local_source_locator` 无空值，`reviewer`/`reviewed_at` 全批一致（2026-10-27T16:18:34+08:00）
- 与原始候选（`round2_candidates_171.pending.bak.jsonl`）逐字段比对：**仅上述 11 条的法条 ID 与 source locator 发生变化**，其余 160 条的题干、题型、难度、知识库范围、法条、弃答标记零改动
- 修订前版本留存为 `round2_candidates_171.review_v1.jsonl`

**注意**：abstain 的 `local_source_locator` 目前是说明性文本（"弃答题（事实不足，不定位具体条文）"），materialize 时若要求可点击的官方来源，仍需替换为对应法律的官方页面 URL。

### 当前 Stage 8 数据状态

| 文件 | 条数 | 状态 |
|---|---|---|
| `review_queue_300.jsonl`（Round1） | 300 | approved 109 / revised 61 / rejected 130 |
| `round2_candidates_171.jsonl`（Round2） | 171 | approved 171 |
| version_or_time 挂起 | 20 | 阻塞：语料版本 + 版本适用规则缺失 |

可用于 materialize 的池子：109（Round1 approved）+ 171（Round2 approved）= **280 条**，其中 20 条 version_or_time 仍需等语料替换后才能补入。

---

## 六、文件清理记录（2026-10-27 16:25）

删除冗余副本前已用 SHA-256 核对内容等价，哈希留存如下，便于追溯：

| 已删除文件 | 等价于 | SHA-256 |
|---|---|---|
| round2_candidates_171_reviewed.jsonl | round2_candidates_171.jsonl | 4D58F442474F1F6DC7B0A75542E6D695ECFA9AF7547C60639C5858C64839C03C |
| review_queue_300_reviewed.jsonl | review_queue_300.jsonl | 0576C3D1D39B6A7BFCC96F454118305EED79D805EB016136B4D239D04E465DB5 |
| review_queue_300 - 副本.jsonl | review_queue_300.pending.bak.jsonl | 079E90A1BC11DAD8C876FCC6EFD2749F7A957CC83176E3E4777A4C05FC4E70ED |
| round2_candidates_171.review_v1.jsonl | 修订前中间版（11 条 revised 状态，内容已在第五节逐条记录） | BC38C604F13780D3B89EFBB65E71558107851F78634CFDC830B003413ED6E4C2 |

保留的权威文件：
- `review_queue_300.jsonl`（300 条，Round1 审核结果）
- `round2_candidates_171.jsonl`（171 条，Round2 审核结果，全部 approved）
- `*.pending.bak.jsonl`（两轮原始未审候选，只读）
- `REVIEW_REPORT_20261027.md`、`REVIEW_WORKFLOW.md`、`README.md`
