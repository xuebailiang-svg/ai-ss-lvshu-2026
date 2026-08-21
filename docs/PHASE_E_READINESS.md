# Phase E 数据核验与准备度实施记录

## 1. 实施结论

Phase E 已把原来的“多来源混合扣分”改为固定、透明的数据准备度目录。准备度回答的是“数据是否足以支持分析”，不是项目推荐概率，也不参与电竞馆选址业务评分。

本阶段没有新增数据库表或字段，没有新增 Alembic migration。

## 2. 固定检查目录

总权重固定为 100：

| 分类 | 检查项 | 权重 |
|---|---|---:|
| 技术前置 | 项目坐标 | 15 |
| 技术前置 | 高德基础采集 | 25 |
| 关键未知 | 疑似竞品清单 | 15 |
| 关键未知 | 核心竞品经营信息 | 20 |
| 关键未知 | 候选物业核心条件 | 15 |
| 建议补充 | 周边配套现场核实 | 10 |
| 可选信息 | 竞品营业额 | 0 |

检查项状态：

- `complete`：已完成。
- `not_applicable`：本次无需补充，例如成功采集后没有竞品候选。
- `acknowledged_unknown`：用户已明确选择不知道，不再重复标红，但报告保留不确定性。
- `missing`：建议或关键数据尚未处理。
- `blocked`：技术前置未完成。
- `optional`：可选信息，不影响准备度。

## 3. 高德采集状态

最近一次采集摘要保存在 `site_projects.raw_data._amap_collection`：

```json
{
  "status": "success_zero",
  "collected_at": "2026-08-12T00:00:00+00:00",
  "poi_count": 0,
  "query_count": 18,
  "failed_query_count": 0,
  "truncated": false,
  "message": "高德采集完成，但当前范围内未返回有效 POI"
}
```

业务规则：

- `not_started`、`needs_confirmation`、`failed` 阻塞正式报告。
- `success_zero` 是有效查询结论，不等同于未采集。
- `partial` 和 `truncated` 可以继续，但报告必须说明覆盖缺口。
- 升级前已有 `source=amap` POI 的项目识别为 `legacy_success`，避免升级后全部被误判为未采集。

## 4. API 返回结构

`GET /api/projects/{project_id}/data-quality`：

```json
{
  "project_id": "proj_xxx",
  "quality_score": 72,
  "missing": ["候选物业核心条件"],
  "warnings": [],
  "readiness": {
    "status": "needs_input",
    "can_generate_report": true,
    "formal_report_ready": false,
    "completion_percent": 72,
    "score_explanation": "准备度按固定检查项权重汇总，不代表项目推荐概率。",
    "amap_collection": {},
    "groups": {
      "technical_prerequisites": [],
      "key_unknowns": [],
      "recommended": [],
      "optional": []
    },
    "summary": {},
    "inventory": {}
  }
}
```

`quality_score` 暂时保留用于旧前端兼容，其值等于 `readiness.completion_percent`，不再使用隐式罚分。

竞品、配套和租金业务明细继续返回，供页面定位人工补充记录，但不参与隐式扣分。以下冻结模块已从核验响应移除：

- `crawler_quality`
- `regional_context_quality`
- `simulation_data_summary`

## 5. 报告守卫

技术前置不完整时：

1. 不调用 DeepSeek 生成正式选址结论。
2. 生成确定性的“电竞馆选址数据不足报告”。
3. 报告仅列出阻塞项和下一步，不推测竞品、客流、收入或盈利。
4. 报告模型标记为 `system-readiness`，便于与真实 AI 报告区分。

普通关键数据缺失不会阻止用户继续，但正式报告必须声明缺失。用户明确标记“不知道”后，该项转为 `acknowledged_unknown`，不会反复显示为红色未处理项。

## 6. 前端展示

项目工作台 Step 4 改为四组业务卡片：

- 技术前置条件
- 关键未知
- 建议补充
- 可选信息

每项显示状态、业务说明和下一步动作。页面明确提示准备度不是推荐概率，不再展示爬虫任务、政府指标、模拟数据或内部技术字段。

## 7. 第一版边界

- 不重新设计选址评分。
- 不让 AI 计算准备度。
- 不把营业额列为必填。
- 不把成功零结果伪装成采集失败。
- 不恢复爬虫、政府统计或模拟数据到 MVP 核验页面。
