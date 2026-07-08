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
| `SITE_FEEDBACK_STORE_PATH` | 本地开发默认 `data/site_feedback.json`；生产固定 `/var/lib/esports-site-selection/site_feedback.json` | feedback event log 本地 JSON 路径。 |
| `AGENT_TRACE_STORE_PATH` | 本地开发默认 `data/agent_traces.json`；生产固定 `/var/lib/esports-site-selection/agent_traces.json` | Agent trace 本地 JSON 路径。 |

生产环境数据持久化路径统一为：

```text
/var/lib/esports-site-selection/site_feedback.json
/var/lib/esports-site-selection/agent_traces.json
```

systemd 服务启用了 `ProtectSystem=strict`，并通过 `ReadWritePaths=/var/lib/esports-site-selection` 授权写入目录。生产环境不要把 trace / feedback 写入 `/opt/esports-site-selection/app/data`。如果 `/etc/esports-site-selection/backend.env` 中也配置了 `SITE_FEEDBACK_STORE_PATH` / `AGENT_TRACE_STORE_PATH`，systemd service 里的 `Environment=` 会覆盖 `EnvironmentFile=` 中的同名变量，生产环境以 systemd service 为准。

前端运行配置文件：

```text
/etc/esports-site-selection/frontend-runtime.json
frontend/dist/config.json
```

其中 `/etc/esports-site-selection/frontend-runtime.json` 通过 Nginx 暴露为 `/runtime-config.json`，`frontend/dist/config.json` 通过 Nginx 暴露为 `/config.json`。这两个路径必须返回 `200 application/json`，不能被 SPA fallback 返回 `index.html`。

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

生产环境 JSON 文件位于：

```text
/var/lib/esports-site-selection/agent_traces.json
```

本地开发未设置环境变量时才使用 `data/agent_traces.json`。

## 6. 如何查看 feedback

feedback 使用 append-only event log，生产环境 JSON 文件位于：

```text
/var/lib/esports-site-selection/site_feedback.json
```

本地开发未设置环境变量时才使用 `data/site_feedback.json`。

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

## 8. 部署后验收

1. 检查服务：

```bash
sudo systemctl status esports-site-selection nginx postgresql --no-pager
```

2. 检查 Health：

```bash
curl -s http://127.0.0.1/api/system/health
```

期望至少包含：

```json
{
  "status": "ok",
  "modules": {
    "trace": true,
    "feedback": true
  },
  "warnings": []
}
```

3. 跑一次 Agent：

检查前端运行配置：

```bash
curl -i http://127.0.0.1/config.json
curl -i http://127.0.0.1/runtime-config.json
curl -I http://127.0.0.1/
```

正确结果：

```text
/config.json                200 application/json
/runtime-config.json        200 application/json
/                            200 text/html
```

如果公网页面一直转圈，优先检查：

```bash
curl -i http://127.0.0.1/config.json
curl -i http://127.0.0.1/runtime-config.json
```

如果 `/config.json` 返回 `index.html`，说明被 SPA fallback 覆盖，需要检查 Nginx `location = /config.json` 是否在 `location /` 之前。如果 `/runtime-config.json` 返回 `403 Forbidden`，优先检查 `/etc/esports-site-selection` 目录权限是否为 `755`、`frontend-runtime.json` 文件权限是否为 `644`。

4. 跑一次 Agent：

```bash
curl -s -X POST http://127.0.0.1/api/agent/site-selection/run \
  -H "Content-Type: application/json" \
  -d '{"city":"西安市","address":"小寨地铁站","radius_meters":1000,"business_type":"电竞馆"}'
```

5. 检查 trace / feedback 生产文件：

```bash
sudo ls -lh /var/lib/esports-site-selection/site_feedback.json /var/lib/esports-site-selection/agent_traces.json
```

6. 检查 Debug API 默认关闭：

```bash
curl -i http://127.0.0.1/api/agent/site-selection/trace/<task_id>
```

生产默认预期返回 `403`。
