# 政府公开数据 Provider

本模块为项目提供城市与区县宏观背景，不提供也不推算项目分析半径内的真实人口、小时客流或客群画像。

## 数据来源

- 国家统计局公开统计公报
- 陕西省统计局公开统计公报
- 西安市统计局公开统计公报
- 管理员上传的官方 CSV、XLSX 或 PDF

采集优先级为结构化文件、HTML、PDF、管理员上传兜底。静态页面使用 `httpx` 和确定性规则解析，不调用大模型补齐统计值。

## 数据状态

- `confirmed`：结构化数据或 HTML 规则校验通过，可进入城市洞察和 AI 报告。
- `pending_review`：PDF 抽取结果，必须由管理员确认。
- `rejected`：已排除，不进入项目上下文。

所有记录必须保留 `source_name`、`source_url`、`stat_period`、`scope_level` 和 `scope_name`。同一指标按“指标、行政区、统计期、来源”执行 upsert。

## 配置

```dotenv
GOV_DATA_ENABLED=true
GOV_DATA_SOURCES=national,shaanxi,xian
GOV_DATA_TIMEOUT_SECONDS=15
GOV_DATA_MAX_RETRIES=2
GOV_DATA_RATE_LIMIT_SECONDS=1
```

政府网站不可访问、页面结构变化或解析为空时，同步失败不能阻断高德采集、评分和报告；系统继续使用已确认的本地缓存。

## API

- `POST /api/projects/{project_id}/collect/government-stats`
- `GET /api/projects/{project_id}/city-insight`
- `POST /api/system/government-stats/sync`
- `GET /api/system/government-stats/review`
- `POST /api/system/government-stats/{record_id}/review`
- `POST /api/system/government-stats/upload`

系统级写操作需要 `X-Admin-Token`。
