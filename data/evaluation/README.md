# LexRAG 检索评测集

每行 JSONL 必须包含：`id`、`query`、`knowledge_base_slug`、`relevant_article_ids`、`source`、`reviewed_at`。

`civil_code_baseline_15.jsonl` 迁自 2026-08-02 已记录的 15 条民法典自建检索基线。它用于回归，当前真实样本数为 **15**，不代表 50 条评测集。扩充时必须逐条人工核验问题与相关法条，再记录来源及复核日期。

运行 `scripts/evaluate_retrieval.py` 时，候选结果文件必须包含每个样本 ID；候选缺失会使命令失败，而不是计作低分。
