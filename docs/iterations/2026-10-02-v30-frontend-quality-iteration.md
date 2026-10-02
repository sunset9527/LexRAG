# LexRAG V3.0：前端体验与工程质量迭代记录

**迭代日期：** 2026-10-02
**范围：** 本机可演示前端体验、质量门禁、测试数据口径
**原则：** 保留既有法律 RAG、证据校验、法规浏览、知识图谱和真实数据接口；不以界面或测试数字替代法律结论。

## 1. 本轮完成内容

### 1.1 前端体验：现代企业 SaaS 工作台

- 建立语义化颜色、字体、间距、圆角、焦点和状态令牌，替换页面级硬编码配色。
- 将深色渐变侧栏改为浅色专业导航；当前页面用淡蓝选中态与左侧标记表达，不再使用大面积深色胶囊样式。
- 移除导航、标题、对话头像和认证页中的结构性 Emoji，统一使用 Element Plus 线性图标。
- 首页改为“法律研究工作台”：突出真实法规、案例、校验与知识库数据，弱化装饰性大卡片。
- 法律咨询页保留会话、回答、法条溯源三栏结构，优化来源检查器、引用视觉层级、窄屏收起策略、焦点状态和减少动态效果。
- 登录、注册、法规浏览与知识图谱入口同步接入新视觉语言。

前端设计规范见：`docs/superpowers/specs/2026-10-02-v30-modern-saas-frontend-design.md`。

### 1.2 工程化测试与质量门禁

新增 `scripts/quality_gate.py`，在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\quality_gate.py
```

该命令按顺序执行并以任一步失败即非零退出：

1. 后端 `pytest tests -q`，同时生成 `app/` 与 `src/` 的覆盖率 JSON；
2. 前端 Node 契约测试；
3. 前端 TypeScript 检查与 Vite 生产构建。

本地报告输出在 `reports/quality/`：

- `latest.json`：机器可读状态、命令、退出码、耗时、截断输出；
- `latest.md`：适合人工查看的门禁摘要；
- `coverage.json`：由 `pytest-cov` 生成的覆盖率明细。

该目录已被 Git 忽略，避免提交用户数据或把一次临时运行结果伪装为永久指标。新增 GitHub Actions 工作流 `.github/workflows/quality.yml`，在 push / PR 上执行同一门禁并上传报告产物。

## 2. 本机真实验证结果

运行时间：2026-10-02；结果来自本机 `reports/quality/` 与既有可审计评测文件。

| 维度 | 本次结果 | 数据来源 |
| --- | ---: | --- |
| 后端自动化测试 | 220 通过 | `reports/quality/latest.json` |
| 前端 Node 契约测试 | 3 通过 | `reports/quality/latest.json` |
| 前端生产构建 | 通过 | `reports/quality/latest.json` |
| 后端行覆盖 | 4,208 / 6,430（65.44%） | `reports/quality/coverage.json` |
| 完整质量门禁耗时 | 38.233 秒 | `reports/quality/latest.json` |
| 民法典检索评测样本 | 15 条人工复核标注 | `data/evaluation/civil_code_baseline_15.jsonl` |
| Recall@5 | 1.0000 | `eval_out/civil_code_baseline_15.json` |
| MRR@5 | 0.9667 | `eval_out/civil_code_baseline_15.json` |
| NDCG@5 | 0.9754 | `eval_out/civil_code_baseline_15.json` |

## 3. 新增的测试保护

- `tests/test_quality_gate.py`：测试质量报告的通过/失败汇总、耗时记录、命令元数据与 Windows 下 `npm.cmd` 启动逻辑。
- `frontend/tests/visualSystem.test.mjs`：检查全局语义令牌存在，并禁止结构性 Emoji、旧深色渐变重新进入应用壳层。
- 既有 `frontend/tests/lawPresentation.test.mjs`：继续验证法规树只展示可用法规库，且不同法律不会复用民法典问题预设。

## 4. 数据解释与边界

- **220 项通过** 表示已定义的自动化回归行为没有失败，不表示所有代码或所有法律场景都被穷尽验证。
- **65.44% 覆盖率** 是测试实际执行的后端行比例，不是功能完成度或法律正确率；未覆盖的 2,222 行是后续补测优先级。
- **Recall@5 = 1.0000** 仅说明这 15 个已人工标注问题中，相关法条都被召回到前 5 条；不能外推为通用法律问答 100% 正确。
- 引用校验通过只说明引用能回溯到本轮证据账本，具体案件仍需结合事实和有效法律版本由专业人士判断。

## 5. 已知警告与后续方向

- 本轮构建仍会提示两个依赖的 Rollup `PURE` 注释，以及 Graph / 主包超过 500KB；不影响构建通过，后续可按路由和 ECharts 模块继续拆包。
- 后端测试有 Pydantic 旧配置、LangChain Community、`pkg_resources` 的依赖弃用提示；当前不阻断测试，但应纳入依赖升级任务。
- 下一步优先补充前端组件/交互测试、外部依赖失败路径和覆盖率较低模块的测试；每项提升都以重新生成的报告为准。
