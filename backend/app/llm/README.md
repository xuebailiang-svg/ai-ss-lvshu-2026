# DeepSeek 大模型报告模块

本模块负责把项目结构化数据和评分结果整理成固定 AI 输入，再调用 DeepSeek 生成 Markdown 报告。

约束：

- 大模型不计算分数，只解释已有评分。
- 不改 Agent 核心流程。
- 不开发爬虫。
- 没有 `DEEPSEEK_API_KEY` 时系统正常启动，接口返回 `success=false`。

环境变量：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

接口：

```http
POST /api/projects/{project_id}/ai-report
```

报告会保存到 `ai_reports`，调用日志会保存到 `ai_call_logs`。
