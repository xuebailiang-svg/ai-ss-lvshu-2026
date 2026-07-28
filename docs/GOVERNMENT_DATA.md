# 政府公开数据与城市洞察

## 目标

政府公开数据用于补充电竞馆选址报告的城市/区县宏观背景，包括人口、经济、产业、消费和就业。它不会替代项目分析半径内的高德 POI、竞品、配套、租金和人工核实数据。

## 真实性边界

- `city` 数据只能描述城市，`district` 数据只能描述区县。
- 禁止把城市或区县指标换算成项目 1km 居住人口、工作人口或小时客流。
- 真实 LBS 数据未接入时，页面和报告必须写明“未接入真实客流数据”。
- HTML/结构化数据校验后可标记 `confirmed`。
- PDF 抽取默认 `pending_review`，管理员确认前不进入 AI 报告事实。
- 每条指标必须保留来源链接、统计年份、空间口径和单位。

## 运行配置

```dotenv
GOV_DATA_ENABLED=true
GOV_DATA_SOURCES=national,shaanxi,xian
GOV_DATA_TIMEOUT_SECONDS=15
GOV_DATA_MAX_RETRIES=2
GOV_DATA_RATE_LIMIT_SECONDS=1
```

配置可由系统配置中心保存，数据库值优先于 `.env`。政府网站同步失败不会阻断高德采集、评分和 AI 报告，系统继续使用已确认缓存。

## 管理操作

配置页“政府公开数据”支持：

- 启用或停用 Provider；
- 数据源连通性测试；
- 按城市/区县强制同步；
- 上传官方 CSV、XLSX 或 PDF；
- 确认或排除 PDF 待审核指标。

系统级写操作需要 `ADMIN_CONFIG_TOKEN`。

## 项目流程

1. 在工作台创建项目，填写城市、区域和地址。
2. Step 3 点击“获取城市公开数据”。
3. 后台同步任务会优先复用 365 天内的年度缓存。
4. “城市洞察”分开展示行政区宏观指标和项目半径内的 POI/配套。
5. AI 报告仅读取 `confirmed` 指标，并附来源、年份与空间口径。

## API

```text
POST /api/projects/{project_id}/collect/government-stats
GET  /api/projects/{project_id}/city-insight
POST /api/system/government-stats/sync
GET  /api/system/government-stats/review
POST /api/system/government-stats/{record_id}/review
POST /api/system/government-stats/upload
```
