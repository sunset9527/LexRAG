# LexRAG 工程质量与评测说明

## 为什么要分开看三类数据

LexRAG 的质量不能用单一“准确率”描述。仓库将其拆成彼此不能替代的三类可复现证据：

| 层级 | 回答的问题 | 当前入口 | 不代表什么 |
| --- | --- | --- | --- |
| 工程回归 | 改动是否破坏已定义的业务、证据、权限和 API 契约 | `scripts/quality_gate.py` | 不能证明法律回答正确 |
| 代码覆盖 | 自动化测试实际执行了多少后端代码行 | `reports/quality/coverage.json` | 不能证明未覆盖路径一定有缺陷 |
| 检索评测 | 人工标注问题的相关法条是否被召回 | `scripts/evaluate_retrieval.py` | 不能代替对回答法律效果的人工复核 |

## 一键工程质量门禁

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
```

它依次执行：

1. `pytest tests -q`，并对 `app/`、`src/` 生成覆盖率 JSON；
2. `node --test` 前端法规展示与视觉系统契约；
3. `npm.cmd run build` 前端生产构建。

若任一步失败，进程以非零状态退出，`latest.json` 会保留每一步的退出码、实际耗时和输出尾部，方便定位失败边界。可用 `--skip-build` 在只调试后端时跳过构建。

## 2026-10-02 本机基线

该基线由上述命令在本机实际运行得到；每次提交前应重新运行，数值可能随代码演进变化。

| 指标 | 实测值 | 证据 |
| --- | ---: | --- |
| 后端自动化测试 | 220 通过 | `reports/quality/latest.json` |
| 前端 Node 契约测试 | 3 通过 | `reports/quality/latest.json` |
| 前端生产构建 | 通过 | `reports/quality/latest.json` |
| 后端行覆盖 | 4,208 / 6,430（65.44%） | `reports/quality/coverage.json` |
| 门禁总耗时 | 38.233 秒 | `reports/quality/latest.json` |
| 民法典检索样本 | 15 条人工复核标注 | `data/evaluation/civil_code_baseline_15.jsonl` |
| Recall@5 | 1.0000 | `eval_out/civil_code_baseline_15.json` |
| MRR@5 | 0.9667 | `eval_out/civil_code_baseline_15.json` |
| NDCG@5 | 0.9754 | `eval_out/civil_code_baseline_15.json` |

## 数据诚信边界

- 15 条检索基线是回归集，不是大样本线上评测，不应写成“法律问答准确率 100%”。
- 引用校验通过只说明引用能在本轮证据账本中找到，不等价于结论在任何事实情境下均正确。
- 质量门禁不发送 API Key；真实工作流评测只在运行时环境变量提供 Key 且人工复核文件存在时单独运行。
