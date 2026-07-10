# 统一数据模型层

`backend/app/data_model/` 定义电竞馆智能选址系统的统一数据标准。来自高德 API、爬虫、第三方接口、人工补充和客户上传的数据，进入评分、AI 分析和报告前都应先转换成这里的 Pydantic 模型。

## 核心约定

- `BaseDataSource` 统一记录 `source`、`timestamp`、`confidence`、`status`、`raw_data`。
- `confidence` 必须在 `0~1` 之间。
- 不能自动获取的字段允许为空，不能因为竞品缺少价格、配置或营业额而拒绝保存。
- 人口相关字段只表示代理指标，不代表真实人口。

## 当前模型

- `SiteProject`：项目基础信息。
- `POIData`：统一 POI。
- `CompetitorData`：电竞馆竞品经营数据。
- `FoodBusinessData`：餐饮和夜间消费数据。
- `EntertainmentData`：娱乐业态数据。
- `RentData`：租金数据。
- `PopulationData`：人口代理指标。
- `SupplementData`：人工补充字段。

## 转换入口

- `convert_amap_poi(raw)`：将高德 POI 转为 `POIData`。
- `convert_manual_competitor(raw)`：将中文字段的人工竞品数据转为 `CompetitorData`。
- `normalize_data(body)`：供 `/api/data/validate` 使用的统一转换入口。
