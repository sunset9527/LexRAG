# 故障排查

## 依赖与启动

- Windows 使用 Python 3.13、Node 22；Python 安装统一使用 `pip install -c constraints-py313.txt -r requirements.txt`，前端使用 `npm ci`。
- `/health/live` 只表示 API 进程存活；`/health/ready` 还会检查 MySQL、迁移、Redis、Embedding、图谱和法规索引。
- Windows 本机 Celery 验收使用 `--pool=solo`；Docker/Linux 使用 Compose 中的 Worker 配置。

## 查询与流式响应

- 浏览器请求经开发代理发送到 API。SSE 使用 `/query-runs/{query_id}/events`，客户端应处理重连、取消和无效事件帧。
- 未设置运行时 LLM Key 时，法律问答不能作为真实模型效果验收；法规浏览、案例库、文档处理和离线检索评测不依赖该 Key。

## 数据与安全

- 不要提交 `.env`、日志、`reports/quality/`、用户上传文件、向量数据库或 API Key。
- 法规版本、来源哈希和索引状态异常时，先检查阶段 4 验证文档与 readiness 响应，不要直接修改 collection 内部数据。
