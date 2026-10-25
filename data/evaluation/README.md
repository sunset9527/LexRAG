# LexRAG 检索评测集

每行 JSONL 必须包含：`id`、`query`、`knowledge_base_slug`、`relevant_article_ids`、`source`、`reviewed_at`。

`civil_code_baseline_15.jsonl` 迁自 2026-08-02 已记录的 15 条民法典自建检索基线。它用于回归，当前真实样本数为 **15**，不代表 50 条评测集。扩充时必须逐条人工核验问题与相关法条，再记录来源及复核日期。

运行 `scripts/evaluate_retrieval.py` 时，候选结果文件必须包含每个样本 ID；候选缺失会使命令失败，而不是计作低分。

`scripts/evaluate_workflow.py` 会对真实 `/query` 逐条执行，并记录校验通过率、标注法条覆盖率、受控修复率与端到端延迟。它从运行时环境变量读取 API Key，报告不保存密钥。`--review` 可传人工断言复核 JSON（`{"civil-001": true}`）；未提供时“断言支持率”会明确显示为空，不能把引用校验当作法律效果结论。

## 八部法律 100 条快照的当前状态

`eight_law_additions_85_draft.jsonl` 的 85 条新增样本仍是 `pending`，没有逐条人工审核记录。

`eight_law_evaluation_100.jsonl` 是历史生成的临时快照。当前生成器曾仅凭一个统一的 `reviewed_at` 日期把 85 条候选批量标记为 `approved`，但 `source` 字段仍明确写着“待人工核验”。因此：

- 该文件不能视为正式人工审核数据集；
- 基于该文件生成的指标只能作为工程调试记录，不能写入 README、简历或对外效果结论；
- 阶段 8 必须补齐逐条审核人、审核日期、来源定位、版本和备注，再重新生成冻结测试集与正式报告；
- 不得为了提高指标修改问题或标签迁就系统输出。

## Stage 5 工程回归样本

`stage5_retrieval_regression.jsonl` 覆盖第 597、633、266 条、`第 X 条之一`、金额/期限、罪名别名和相邻/引用法条。样本定位到本地已确认法规原文，但尚未完成逐条人工标签审核，因此运行 `scripts/evaluate_multikb_retrieval.py` 产出的报告标记为 `engineering_regression`，不能作为正式检索效果指标。
