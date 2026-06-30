# v1.0 Runbook

本手册用于 v1.0 freeze candidate 的启动、检查、调试和运维。当前系统不接入 LangChain / LangGraph / LLM API。

## 1. 项目启动方式

### Backend 启动

本地开发：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[test]"
uvicorn app.main:app --reload --port 8000
```

Ubuntu 直接部署：

```bash
cd /home/ubuntu/data/ai-ss-lvshu-2026-main
bash scripts/deploy.sh
sudo systemctl restart esports-site-selection
```

### Frontend 启动

本地开发：

```bash
cd frontend
npm install
npm run dev
```

生产构建：

```bash
cd frontend
npm run build
```

## 2. 环境变量说明

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AMAP_WEB_SERVICE_KEY` | 空 | 后端高德 Web 服务 Key。生产环境应配置真实 Key。 |
| `AMAP_MOCK` | `false` | 是否使用 mock 高德数据。演示或测试环境可设为 `true`。 |
| `ENABLE_TRACE` | `true` | 是否记录 Agent trace。写入失败不影响主流程。 |
| `ENABLE_FEEDBACK` | `true` | 是否启用 feedback event log 和回填接口。 |
| `ENABLE_REFLECTION` | `true` | 是否启用 Reflection 决策校准。 |
| `ENABLE_SIMILAR_CASES` | `true` | 是否启用相似案例检索。该能力仍标记为 experimental。 |
| `ENABLE_DEBUG_API` | `false` | 是否开放 trace debug API。生产默认关闭。 |
| `SITE_FEEDBACK_STORE_PATH` | `data/site_feedback.json` | feedback event log 本地 JSON 路径。 |
| `AGENT_TRACE_STORE_PATH` | `data/agent_traces.json` | Agent trace 本地 JSON 路径。 |

## 3. 核心 API 使用

### Agent Run API

```http
POST /api/agent/site-selection/run
```

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/agent/site-selection/run \
  -H "Content-Type: application/json" \
  -d '{
    "city": "西安市",
    "address": "雁塔区小寨西路",
    "radius_meters": 1000,
    "business_type": "电竞馆"
  }'
```

### Feedback API

```http
POST /api/feedback/site-result
```

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/feedback/site-result \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "替换为 Agent 返回的 task_id",
    "actual_result": "profit",
    "notes": "真实经营情况",
    "monthly_revenue_range": "10-20万"
  }'
```

### Health API

```http
GET /api/system/health
```

示例：

```bash
curl http://127.0.0.1:8000/api/system/health
```

## 4. Agent 执行流程说明

当前执行链：

```text
planner
→ tools
→ scoring
→ similar_case_search（experimental，可关闭）
→ report_generate
→ reflection
→ feedback event log
→ trace
```

其中：

- `planner`：rule-based，不调用 LLM；
- `tools`：高德真实数据 + fallback；
- `reflection`：规则化决策校准，不是投资建议；
- `feedback`：append-only event log；
- `trace`：完整执行链，用于回放和调试。

## 5. 如何查看 trace

生产默认关闭 Debug API。开发环境开启：

```env
ENABLE_DEBUG_API=true
```

重启后端后调用：

```bash
curl http://127.0.0.1:8000/api/agent/site-selection/trace/<task_id>
```

本地 JSON 文件默认位于：

```text
backend/data/agent_traces.json
```

或由 `AGENT_TRACE_STORE_PATH` 指定。

## 6. 如何查看 feedback

feedback 使用 append-only event log，本地 JSON 默认位于：

```text
backend/data/site_feedback.json
```

或由 `SITE_FEEDBACK_STORE_PATH` 指定。

事件类型：

- `agent_run_completed`
- `feedback_initialized`
- `feedback_updated`

## 7. 如何调试 Agent（仅开发模式）

1. 设置：

```env
APP_ENV=development
ENABLE_DEBUG_API=true
ENABLE_TRACE=true
AMAP_MOCK=true
```

2. 启动后端：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

3. 运行 Agent：

```bash
curl -X POST http://127.0.0.1:8000/api/agent/site-selection/run \
  -H "Content-Type: application/json" \
  -d '{"city":"西安市","address":"雁塔区小寨西路","radius_meters":1000,"business_type":"电竞馆"}'
```

4. 使用返回的 `task_id` 查询 trace。

注意：生产环境不建议开启 `ENABLE_DEBUG_API`。
