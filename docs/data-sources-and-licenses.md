# 数据来源与授权说明

## 代码、数据和模型必须分开理解

本仓库当前没有授予开源代码许可证。即使未来代码采用开源许可证，法律文本、案例汇编、用户上传文件、本地模型权重和第三方 API 也不会自动随之授权。

## 法规与案例

- 法规原件、版本线索、SHA-256 与人工核验记录以仓库内法规 manifest、版本链和阶段 4 验证文档为准；展示和检索仅用于法律信息学习，不构成法律意见。
- 年度案例汇编明确标记为用户提供的本地资料，不表述为最高人民法院指导案例或典型案例。
- 用户上传的 PDF/DOCX 属于所属组织的数据；不得提交到 Git、评测 artifact 或公开 issue。

## 依赖、模型和服务

- Python/npm 依赖各自遵守其许可证；当前 CI 尚未配置许可证允许清单，发布前仍须完成人工复核或接入许可证扫描。
- BGE-M3、OCR、向量数据库和 LLM 服务分别受其模型、服务和平台条款约束。运行时 API Key 仅可通过受控配置注入，不得进入仓库、日志或测试报告。

## 可复核入口

数据版本与来源边界：`docs/status/stage-4-legal-version-verification.md`；工程质量边界：`docs/engineering-quality.md`；完整历史路线以维护者单独维护的《RAG法律.md》为准。

## 依赖审计记录（2026-10-26）

- 已实际运行修复前 `npm audit --json`，原始报告保存在本地忽略目录 `reports/security/npm-audit.json`：前端锁文件有 **17** 项发现（**2 critical、9 high、6 moderate**）。随后在 Node `24.22.1` / npm `11.19.1` 下执行了**不带 `--force`** 的 `npm audit fix`，并生成修复后报告 `reports/security/npm-audit-post-fix.json`：剩余 **8** 项（**2 critical、6 moderate、0 high**）。本次非破坏性更新覆盖 Vue、Axios、Vite、Markdown-it、PostCSS、source-map 与相关传递依赖；前端单元测试（6/6）、生产构建和真实 Chromium 登录页 E2E（1/1）均通过。
- 剩余 8 项不能被普通修复安全消除：`vitest`/`tinypool`（2 critical，开发/CI 测试链）需升至 Vitest 5；`echarts`/`vue-echarts`（生产依赖）需协同主版本升级；`tailwindcss` 与其 PostCSS 链需升至 Tailwind 4。它们均保持为公开风险，禁止用 `npm audit fix --force` 或只改 lockfile 的方式关闭；每个 major 升级必须作为独立兼容性任务，带组件/构建/E2E 回归。
- `.nvmrc` 仍声明 Node 22；为避免卸载用户既有 Node 24 工具链，本机受控升级至 Node `24.22.1`，满足此前 `EBADENGINE` 所要求的 `>=24.15.0`。这证明当前本机修复与验证有效，但**不替代** Node 22 CI 的持续验证；后续 CI 不应因这一本机偏差而移除 Node 22。
- 已实际运行 `python -m pip_audit --local --format json`，结果保存在本地 `reports/security/python-audit.json`：共享 `E:\python` 解释器的 288 个已安装包中，有 38 个包、324 条原始发现。该解释器包含项目外工具和包，且已安装版本与 `requirements.txt` / `constraints-py313.txt` 不完全一致，故**不能把 324 直接表述为 LexRAG 漏洞数**。其中与项目直接依赖相交的风险信号至少涉及 `chromadb`、`langchain`、`langgraph`、`pydantic-settings`、`python-dotenv`、`python-jose` 与 `torch`；必须在干净的、按项目依赖安装的 Python 3.13 环境复审并逐项确定可用修复版本，之后才能升级或关闭发现。
- 已在一次性 Python 3.13 隔离环境中按 `requirements.txt` 与 `constraints-py313.txt` 实际安装后运行 `pip-audit`，结果为 201 个依赖、3 个受影响包、8 条原始记录（去重后 6 个 advisory ID），报告保存在 `reports/security/python-audit-isolated.json`。`chromadb==1.5.9` 对应 5 条记录（其中一条 advisory 重复），均无上游可用修复版本；其风险涉及远程 Chroma 的模型加载和多租户授权。当前代码仅构造本地 `PersistentClient`，未暴露 Chroma 远程多租户 API，故归为**高优先级架构边界风险**：在引入远程 Chroma、外部模型仓库或多租户前必须重新评估/隔离，不能标记为已修复。
- `python-jose==3.5.0` 有 1 条无可用修复版本的非对称公钥/HS256 混淆 advisory。当前 `app/services/auth_service.py` 在签发时固定 `HS256`，验证时使用 `algorithms=["HS256"]`，因此不满足该 advisory 所述“未显式限制算法”的利用前提；归为**已在实现层缓解、但仍需跟踪上游版本**。`ecdsa==0.19.2` 的 2 条记录是同一无修复时序攻击 advisory；项目 JWT 路径不调用其受影响的 P-256 签名、密钥生成或 ECDH API，归为**低优先级接受风险**，以后若引入 ECDSA 私钥签名必须改用抗侧信道实现。
- 已实际运行 `python -m piplicenses --format=json`，生成 283 个当前解释器包的许可证清单 `reports/security/python-licenses.json`。项目直接依赖中最需要处理的是 **PyMuPDF**：工具报告为“AGPL-3.0 或 Artifex 商业许可”双许可。若未来公开发布、分发或商业部署包含该依赖，必须在采用 AGPL 义务、取得商业许可或替换实现之间作出书面决定；在此之前不得表述为已完成开源许可证合规。其余当前直接依赖的工具报告主要为 MIT、BSD、Apache-2.0 类许可。
- 隔离环境的许可证清单 `reports/security/python-licenses-isolated.json` 覆盖 196 个已安装包，结论与共享环境一致：主要为 MIT、Apache、BSD、PSF、MPL 等许可；唯一需要发布/商业决策的直接解析器依赖仍为 `pymupdf==1.28.2` 的 AGPL-3.0 / Artifex 商业双许可。该结论是项目范围证据，优先于共享解释器的许可证数量。
- 已从 `frontend/package-lock.json` 生成 `reports/security/npm-licenses.json`：333 个包以 MIT、ISC、Apache-2.0、BSD、BlueOak、Python-2.0 等宽松许可证为主；唯一非软件宽松许可条目为 `caniuse-lite` 的 CC-BY-4.0，应保留其署名要求。`lexrag-frontend` 本身显示 `UNLICENSED`，这与本仓库当前未授予开源代码许可证的声明一致，不可误读为第三方依赖问题。
