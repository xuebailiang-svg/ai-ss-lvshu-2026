## M1.5 API 补充

- `GET /api/health/config`：返回高德和大模型配置状态，只返回是否已配置，不返回密钥。M1.5 中 `llm_enabled=false`，报告不调用大模型。
- `GET /api/evaluations`：支持 `city`、`q`、`recommendation`、`has_hard_risk`、`sort_by`、`order` 筛选和排序。
- `PUT /api/evaluations/{id}/property`：保存物业调查表，并自动换算租金指标。
- `POST /api/evaluations/{id}/score`：重新评分；保留原始 POI 和人工调研数据，更新评分结果和报告。
- `PUT /api/competitors/{poi_id}/enrichment`：保存或更新某个竞品 POI 的最新人工调研摘要，同时写入一条调研历史记录。
- `GET /api/competitors/{poi_id}/enrichments`：查看竞品最新调研和历史调研记录。
- `POST /api/evaluations/compare`：传入 2～5 个评估 ID，返回地址对比表数据。

竞品人工调研字段包括机器数量、面积、CPU、显卡、显示器、价格、充值优惠、推测开业时间、开业依据、上座率、调查时间、调查方式、数据来源、可信度、人工核实状态和备注。上座率属于人工估算时，报告会标注为“估算值”。

物业调查字段包括面积、楼层、层高、租金、物业费、转让费、押金、免租期、租期、供电、网络、夜间出入口、业态许可、消防、喷淋、排烟、安全出口、停车、门头、噪声风险、整改事项、联系人、调查时间、来源、可信度和备注。

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
