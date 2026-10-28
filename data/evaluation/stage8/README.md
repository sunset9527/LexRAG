# Stage 8 frozen evaluation set

`stage8_reviewed_baseline_280.jsonl` 是 280 条人审候选基线，不是正式评测集；原始审核快照与该基线必须保持只读。正式数据由 `scripts/snapshot_stage4_provenance.py` 在显式 `as_of` 日期导出 Stage 4 已核验来源快照，再由 `scripts/materialize_stage8_frozen_dataset.py` 确定性生成。

正式行使用 `source_evidence` 列表：每个预期知识库 slug 恰有一条来源证据，跨法问题因此保留多个真实版本、URL、内容哈希、法条分区和定位。只有 280 行全部为 `approved` 且通过 `src.evaluation.stage8_dataset` 校验后，输出才是正式冻结数据。

冻结数据证明的是法律标签及其来源版本可追溯，不等于检索准确率、回答正确率或现行法效果结论。任何性能指标仍须在冻结数据上独立运行、记录并复现；不得编造或为提高指标而修改标签。

## 2026-10-27 正式冻结产物

- `stage4_provenance_2026-10-27.json`：8 部法律在 `as_of=2026-10-27` 的已核验版本、collection 身份及法条目录快照。
- `stage8_frozen_280.jsonl`：280 条全部通过正式 Schema 的 approved 样本，含 320 条来源证据和 460 个法条标签；40 条跨法样本各保留两条来源证据，20 条为弃答样本。
- `stage8_frozen_280.manifest.json`：绑定 baseline、Stage 4 快照和正式 JSONL 的原始字节 SHA-256；正式数据集 SHA-256 为 `de1ea5f227ef005dbf964555d837b54db549610a5c92b979c579882a5fef7a33`。

这些事实由 `tests/test_stage8_frozen_artifacts.py` 持续校验。它们仍只代表冻结标签来源完整性，不构成任何检索或回答效果声明。

## 正式检索与路由评测

在项目根目录运行独立入口；`--persist-directory` 填入保存上述快照 collection 的现有 Chroma 目录。每次只能选择 `vector`、`bm25`、`rrf` 中的一种模式，输出路径必须位于 Chroma 目录之外。

```powershell
python scripts/evaluate_stage8_formal_retrieval.py `
  --dataset data/evaluation/stage8/stage8_frozen_280.jsonl `
  --snapshot data/evaluation/stage8/stage4_provenance_2026-10-27.json `
  --frozen-manifest data/evaluation/stage8/stage8_frozen_280.manifest.json `
  --persist-directory <现有Chroma目录> `
  --mode vector `
  --output <报告路径.json>
```

入口必须读取冻结 manifest，核对数据集和快照的原始字节 SHA-256、各法律来源身份及统计，并确认实际数据为 280 行（260 条可回答、20 条弃答）、320 条来源证据、460 个标签。任意 approved 子集或缩减快照均不能作为正式评测输入；不支持手动覆盖 collection。

单个 JSON 报告分别记录 oracle 检索和当前自动路由结果，附带冻结 manifest 引用、快照身份、Git commit、Python 和相关依赖版本。报告不评价回答质量或弃答准确率。输入校验或写入失败时保留已有输出；报告使用临时文件完成后原子替换。
