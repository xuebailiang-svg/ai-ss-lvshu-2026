# Product Boundary v1.0

本文定义 v1.0 freeze candidate 的产品能力边界。当前版本定位为“可部署、可交付、可运行”的电竞馆选址 Agent baseline。

## 1. 对外开放能力

### Agent Run API

```http
POST /api/agent/site-selection/run
```

用途：

- 输入城市、候选地址、半径、业态；
- 返回规划、执行步骤、评分、报告、Reflection、feedback 初始化结果；
- 作为 v1.0 的核心对外能力。

### Feedback API

```http
POST /api/feedback/site-result
```

用途：

- 回填真实经营结果；
- 支持 `profit`、`loss`、`unknown`；
- 写入 append-only event log。

### Health API

```http
GET /api/system/health
```

用途：

- 检查 tools、trace、feedback、amap、planner 是否可用；
- 返回版本号和配置开关状态；
- 作为部署和运维验收入口。

### Frontend runtime config

```http
GET /config.json
GET /runtime-config.json
```

用途：

- `/config.json` 返回前端 API 基础路径，例如 `{"apiBaseUrl":"/api"}`；
- `/runtime-config.json` 返回前端公开运行配置；
- 两者均为公开配置，不允许放入后端私密 Key、数据库连接、Token 或密码；
- 生产部署必须返回 `200 application/json`，不能被 SPA fallback 返回 `index.html`。

## 2. 内部能力（默认不对外暴露）

### Trace Debug API

```http
GET /api/agent/site-selection/trace/{task_id}
```

边界：

- 仅当 `ENABLE_DEBUG_API=true` 时开放；
- 生产默认关闭；
- 用于开发调试、问题复盘和执行链回放；
- 不建议作为业务前端依赖接口。

### Tool internal output

边界：

- `steps[].output` 和 trace 中的 tool output 用于诊断；
- 不作为稳定对外业务契约；
- 对外展示应优先使用 report、score、reflection 和 health。

### Planner reasoning detail

边界：

- `plan_reasoning` 用于解释 rule-based planner；
- 不代表大模型推理；
- 不应包装成“AI 自主推理结论”。

## 3. 模式说明

### Production mode

建议配置：

```env
APP_ENV=production
AMAP_MOCK=false
ENABLE_TRACE=true
ENABLE_FEEDBACK=true
ENABLE_REFLECTION=true
ENABLE_SIMILAR_CASES=true
ENABLE_DEBUG_API=false
```

行为：

- Agent Run API 可用；
- Feedback API 可用；
- Health API 可用；
- Trace 会在后端记录；
- Trace Debug API 返回 `403`；
- 前端默认不展示 Trace Debug UI。

### Development mode

建议配置：

```env
APP_ENV=development
AMAP_MOCK=true
ENABLE_TRACE=true
ENABLE_FEEDBACK=true
ENABLE_REFLECTION=true
ENABLE_SIMILAR_CASES=true
ENABLE_DEBUG_API=true
```

行为：

- 可查看完整 trace；
- 可使用 mock 数据快速调试；
- 可验证 feedback event log；
- 可通过前端 Trace Viewer 查看执行链。

## 4. 明确不包含的能力

v1.0 不包含：

- LangChain / LangGraph；
- LLM API；
- 多 Agent 自主规划；
- 自动营收预测；
- 多租户；
- 用户系统；
- 权限系统；
- API Key 管理后台；
- 数据库版 feedback/trace 存储。

这些能力如需进入产品路线，应作为 v1.1+ 或独立里程碑处理。
