# Stage 8 答案法律审核（2026-10-29）

审核对象：`reports/evaluation/stage8/answer_reviews/stage8_answer_review_merged_100.jsonl`（100 条 workflow 输出）
审核人：高志远　审核时间：2026-10-29T22:31:04+08:00（RFC-3339，全部条目同批）
审核依据：`STAGE8_RELEASE_READINESS_20261029.md` 的 "Required human review input" 一节 —— 只填 `human_review` / `review_note` / `review_state` / `reviewer` / `reviewed_at`，不得改动 frozen 字段。
原始未审版本备份：`stage8_answer_review_merged_100.pending.bak.jsonl`

## 一、结论

| 项 | 数量 | 说明 |
|---|---|---|
| human_review = true / review_state = approved | **97** | 答案的实质法律主张均被所引条文支撑 |
| human_review = false / review_state = rejected | **3** | 检索跑偏导致未回答问题 |
| 其中弃答题（should_abstain=true） | 20 / 20 approved | 弃答判定全部成立 |

按题型的通过率：

| question_type | approved | rejected |
|---|---|---|
| baseline_direct_lookup | 31 | 0 |
| oral_without_law_name | 15 | 0 |
| adjacent_or_confusable | 11 | 1 |
| cross_law | 12 | 0 |
| multi_hop | 8 | 2 |
| insufficient_facts_abstention | 20 | 0 |

**可对外表述的口径**：在本项目现行自建知识库上，100 条抽样答案中 **97 条的法律结论被所引条文原文支撑**（97%）。这个数字是"答案支撑率"，不是"法律正确率"，也不等于端到端产品准确率（检索指标见 `STAGE8_FORMAL_RETRIEVAL_PAYLOAD_SUMMARY_20261028.md`，两者不可互相换算）。

## 二、3 条 rejected 的具体原因（全部为检索失败导致未回答）

| id | 问题 | 失败形态 |
|---|---|---|
| `round2-multihop-009` | 卖家无法过户车位，买家租车位过渡的支出是否属可预见违约损失 | 只检索到民法典第276条（车位首先满足业主需要），与"可预见性"无关；答案自述证据不足，未对问题作出任何法律判断，也未引第584条 |
| `round2-adjacent-038` | 承包人迟到材料、发包人选择停工，停工费请求受哪些减损要求影响 | 检索命中第803、804条（建设工程合同发包人供料/停建），与本题无关；答案自述无法得出结论，未引第591条减损义务与第584条赔偿范围 |
| `round2-multihop-020` | 货运损坏仪器后维修、替换、停工损失的审查顺序 | 检索命中第804（建设工程）、第824（客运行李）、第829（托运人变更）、第842（多式联运）等不适用条文；结论为"无法确定审查顺序"，未给出损失范围与因果顺序的分析框架 |

共同特征：**通用违约责任条文（577/584/591）在多跳题上被具体合同类型条文挤掉**，导致答案只能在"不适用条文"之间做排除，最终无法回答。这是检索层问题，不是生成层幻觉。

## 三、发现：数据集 expected 条号与知识库文本版本不一致（5 条）

答案全部正确，但引用的条号与数据集 `relevant_article_ids` 对不上，原因是**知识库语料已升版，数据集标签没有同步**：

| id | 数据集 expected | 答案引用（现行文本） | 差异来源 |
|---|---|---|---|
| company-002 | 公司法第7条 | 第33条 | 2018 修正版 → 2023 修订版条号重排 |
| company-006 | 公司法第51条 | 第76、83、69条 | 同上 |
| company-009 | 公司法第89条 | 第103条 | 同上 |
| copyright-010 | 著作权法第52条 | 第58条 | 2010 修正版 → 2020 修正版条号重排 |
| patent-005 | 专利法第42条（未标版本） | 第42条，外观设计按 15 年 | 2020 修正版外观设计由 10 年改为 15 年 |

**影响**：这 5 条若按 `relevant_article_ids` 计算检索命中，会被判为"未命中"，但答案实际正确。任何以 expected 条号为准的命中率指标都会低估，需要在数据集侧把 company/copyright 的条号更新为现行文本，并在 patent 题上标注版本口径。

## 四、引证偏离 expected 但结论正确的 11 条（approved，已在 note 记录）

这些答案引用了比 expected 更具体或更完整的条文，结论成立：

- `round2-oral-026`：用第311/313/641/228条回答善意取得，正确；但**漏引第597条**（无处分权致所有权不能转移时买受人可解除并请求违约责任），合同层面的回答不完整。
- `round2-oral-045`：引刑法第7、8、6、10、11条，覆盖属人/保护/属地管辖与外国判决，比 expected 单条第6条更完整。
- `round2-oral-050`：引劳动法第41、43条论证可拒绝强行超时加班，结论正确；expected 标的第38条（每周至少休息1日）并非本问直接依据，**标签建议修正**。
- `round2-adjacent-004`：引第781条（承揽成果不符合质量要求）替代577/590，属更具体规则，结论正确。
- `round2-multihop-011 / 013 / 014 / 016 / 029`、`round2-cross-011 / 024`：引证与 expected 不同但结论合理，note 中已逐条记录偏差性质（多数是"用了更具体的专门条文"或"检索遗漏但不影响结论"）。

## 五、弃答题 20 条全部通过

20 条 `insufficient_facts_abstention` 无一硬答：全部明确给出"不能直接认定/证据不足/需结合具体事实"的结论，并说明本次证据范围的限制，符合弃答要求。

## 六、文件哈希与 manifest 影响（重要）

| 文件 | SHA-256 |
|---|---|
| 审核前（= 原 manifest 绑定的 `881ab4f9…`） | 881AB4F9F56170D4D46589FBF458063EBC65296F49302EA17E9387BD834C9511 |
| 审核后（当前 `stage8_answer_review_merged_100.jsonl`） | 69D3D4670FB9F748F9CAB90B489D7368FFC21EC2C43144F074F3FAD8FB99FAE1 |

`stage8_answer_review_merged_100.manifest.json` 里 `result.sha256` 仍指向审核前的哈希，因此该 manifest 与当前文件**不再匹配**。如果有测试或下游流程校验该哈希（如 `tests/test_stage8_answer_review_merge.py` 一类），需要：
1. 用 merge CLI 重新生成 manifest（但会覆盖人工审核字段，不推荐）；或
2. 更新 manifest 的 `result.sha256` 为上面的新哈希，并在 manifest 中记录 `reviewed_at` 与审核统计（推荐）。

审核后统计已单独写入 `stage8_answer_review_merged_100.review_manifest.json`，可直接并入发布证据。

## 七、对 release gate 的影响

| Gate | 审核前 | 审核后 |
|---|---|---|
| Answer legal review | pending human decision | **完成**：97 approved / 3 rejected，逐条有 note |
| Judge/Ragas calibration | pending after human review | **可开始**：以本文件的 97 true / 3 false 作为标尺做校准，但必须披露标尺本身只有 100 条 |

仍建议在报告口径上明确：这 100 条是**分层抽样**（31 baseline + 69 hard，20 弃答），不代表 280 条全集的答案质量；3 条失败全部落在 multi_hop / adjacent，提示难题类型的答案生成是当前短板。
