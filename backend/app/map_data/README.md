# 高德地图数据采集模块

本模块把现有高德能力拆成独立的数据采集服务，服务于 `site_projects`。

职责划分：

- `amap_client.py`：调用高德 `place/around` API。
- `mapper.py`：调用 `app.data_model.converters`，把高德 POI 转为统一数据模型。
- `service.py`：读取项目、执行采集、去重 upsert、保存到 `pois` 表。
- `router.py`：提供项目级采集接口。

当前阶段只采集 POI，不接入 DeepSeek，不做爬虫，不修改评分模型、报告生成或 Agent 核心流程。

接口：

```http
POST /api/projects/{project_id}/geocode
POST /api/projects/{project_id}/collect/amap
```

- `POST /geocode`：仅解析项目地址并写入经纬度，不采集任何 POI。用于工作台 Step 2「解析并确认地址」，保证 Step 3 采集前地址已确认。
- `POST /collect/amap`：若项目尚无经纬度，会先自动解析地址再采集 POI。

营业时间说明：高德 `place/around` 接口把营业时间放在 `biz_ext.open_time`（可能是字符串或数组），
统一由 `app.data_model.converters._amap_business_hours` 提取并规范为字符串后写入 `business_hours` 列。

配置：

- 生产环境通过 `/etc/esports-site-selection/backend.env` 注入 `AMAP_WEB_SERVICE_KEY`。
- 如果未配置 Key 且未启用 `AMAP_MOCK=true`，接口返回 `success=false` 和 `AMAP_WEB_SERVICE_KEY未配置`。
