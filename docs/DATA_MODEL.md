# 数据模型

- `site_evaluations`：评估主记录与任务状态。
- `candidate_sites`：标准地址、GCJ-02 原始坐标及提供商。
- `property_surveys`：物业、租金、供电和消防人工调查。
- `poi_observations`：高德 POI、类型码、距离、原始响应和数据质量。
- `competitor_enrichments`：竞品机器、配置、价格、上座率人工补充，与高德层隔离。
- `regulation_rules`：城市、敏感类型、距离、风险和政策依据。
- `scoring_models`、`scoring_results`：可配置规则版本及评分证据。
- `evaluation_reports`：结构化标准报告。
- `data_sources`：数据源登记。

高德坐标保存为 `GCJ02`，不伪装为 WGS84。空间字段待明确转换流程后引入 PostGIS geometry。
