# API

- `GET /api/health` 健康检查
- `POST/GET /api/evaluations` 创建、筛选历史评估
- `GET /api/evaluations/{id}` 获取评估、POI 和评分
- `POST /api/evaluations/{id}/geocode` 地址定位
- `POST /api/evaluations/{id}/collect-pois` 采集 POI
- `POST /api/evaluations/{id}/score` 生成评分并保存报告
- `GET /api/evaluations/{id}/report` 获取报告
- `PUT /api/competitors/{id}/enrichment` 保存竞品人工补充
- `GET /api/regulation-rules` 获取规则

交互文档在后端 `/docs`。采集状态为 `pending/running/completed/failed`；上游失败返回 HTTP 502，未满足前置条件返回 HTTP 409。
