# 外部数据源插件框架

`app.data_source` 是外部数据采集能力与现有业务服务之间的适配层。它不负责数据库写入，也不改变现有高德采集和 CSV 上传接口。

## 统一边界

- `DataProvider`：定义 POI、竞品、餐饮、娱乐和租金的统一方法。
- `DataSourceRequest`：统一传递项目位置、半径和待转换记录。
- `ProviderResult`：统一返回调用状态、统一模型数据、警告和元数据。
- `DataSourceRegistry`：按来源注册和加载 Provider。

所有 Provider 输出均使用 `app.data_model` 中的 `POIData`、`CompetitorData`、`FoodBusinessData`、`EntertainmentData` 或 `RentData`，不得自行重复定义业务字段。

## 当前状态

| 来源 | Provider | 状态 |
| --- | --- | --- |
| 高德地图 | `AmapProvider` | 配置 Key 或 Mock 后可用 |
| 人工上传 | `ManualUploadProvider` | 可用 |
| 爬虫 | 占位 Provider | 禁用，未实现 |
| 第三方数据 | 占位 Provider | 未配置，未实现 |

后续新增数据源时，实现 `DataProvider`、注册到 `DataSourceRegistry`，并继续复用 `app.data_model.converters`。
