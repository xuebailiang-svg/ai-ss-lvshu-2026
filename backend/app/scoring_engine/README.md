# 电竞馆智能选址评分引擎

本模块是独立评分引擎，只输出结构化评分数据，不生成 AI 报告。

职责：

- `default.yaml`：评分权重和规则配置。
- `rules.py`：读取 YAML 配置。
- `calculator.py`：根据项目 dataset 计算分数、风险、缺失项和置信度。
- `service.py`：读取项目数据、执行评分、保存评分历史。
- `router.py`：提供项目评分 API。

接口：

```http
POST /api/projects/{project_id}/score
```

当前一级指标：

- 人口因素：30 分
- 交通因素：20 分
- 夜经济和配套：20 分
- 竞品因素：20 分
- 成本因素：10 分

约束：

- 不接 DeepSeek。
- 不生成 AI 报告。
- 不修改 Agent。
- 不开发爬虫。
