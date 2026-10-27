# Stage 8 frozen evaluation set

`stage8_reviewed_baseline_280.jsonl` 是 280 条人审候选基线，不是正式评测集；原始审核快照与该基线必须保持只读。正式数据由 `scripts/snapshot_stage4_provenance.py` 在显式 `as_of` 日期导出 Stage 4 已核验来源快照，再由 `scripts/materialize_stage8_frozen_dataset.py` 确定性生成。

正式行使用 `source_evidence` 列表：每个预期知识库 slug 恰有一条来源证据，跨法问题因此保留多个真实版本、URL、内容哈希、法条分区和定位。只有 280 行全部为 `approved` 且通过 `src.evaluation.stage8_dataset` 校验后，输出才是正式冻结数据。

冻结数据证明的是法律标签及其来源版本可追溯，不等于检索准确率、回答正确率或现行法效果结论。任何性能指标仍须在冻结数据上独立运行、记录并复现；不得编造或为提高指标而修改标签。
