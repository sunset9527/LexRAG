# LexRAG 检索评测集

每行 JSONL 必须包含：`id`、`query`、`knowledge_base_slug`、`relevant_article_ids`、`source`、`reviewed_at`。

`civil_code_baseline_15.jsonl` 迁自 2026-08-02 已记录的 15 条民法典自建检索基线。它用于回归，当前真实样本数为 **15**，不代表 50 条评测集。扩充时必须逐条人工核验问题与相关法条，再记录来源及复核日期。

运行 `scripts/evaluate_retrieval.py` 时，候选结果文件必须包含每个样本 ID；候选缺失会使命令失败，而不是计作低分。

`scripts/evaluate_workflow.py` 会对真实 `/query` 逐条执行，并记录校验通过率、标注法条覆盖率、受控修复率与端到端延迟。它从运行时环境变量读取 API Key，报告不保存密钥。`--review` 可传人工断言复核 JSON（`{"civil-001": true}`）；未提供时“断言支持率”会明确显示为空，不能把引用校验当作法律效果结论。
