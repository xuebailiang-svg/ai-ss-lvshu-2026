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

AI 输入中的 `competitor_analysis` 直接来自最近一次评分结果，不在报告阶段重新计算。经营均值只代表已确认竞品，待核实竞品只能作为数量参考，已排除竞品不会进入 AI 上下文。缺失的价格、配置、上座率等字段保持为空，并要求报告明确提示补充。

AI 输入中的 `supporting_analysis` 同样直接来自最近一次评分结果。报告阶段不重新统计 POI，也不会把待核实或已排除配套描述为事实；便利店、餐饮和娱乐场所的夜间经营状态必须以人工确认数据为准。

AI 输入中的 `rent_analysis` 直接来自最近一次评分结果。报告阶段不重新查询或计算 `rent_data`，仅使用评分阶段筛选后的已确认有效租金样本；待核实和已排除租金不会发送给 AI。报告必须披露样本数量、平均单价、压力等级及完整度，不得推测城市租金水平、营业收入或盈利结果。
