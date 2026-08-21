# 数据模型基线

## MVP 主模型

| 模型/表 | 状态 | 用途 |
|---|---|---|
| `SiteProjectRecord` / `site_projects` | KEEP | 唯一项目主记录，保存地址、坐标、半径和项目状态 |
| `UnifiedPOIRecord` / `pois` | KEEP | 高德 POI 事实基础 |
| `UnifiedCompetitorRecord` / `competitors` | KEEP | 疑似竞品与人工调查详情 |
| `FoodBusinessRecord` / `food_businesses` | KEEP | 餐饮 POI 与必要人工核实 |
| `EntertainmentRecord` / `entertainments` | KEEP | 娱乐 POI 与必要人工核实 |
| `RentDataRecord` / `rent_data` | SIMPLIFY | 收敛为候选物业实际租金和条款，不做外部市场租金 |
| `SupplementRecord` / `supplements` | SIMPLIFY | 项目级补充信息，避免与业务记录重复 |
| `ManualInputRecord` / `manual_inputs` | SIMPLIFY | 人工修改审计与来源记录 |
| `AIReportRecord` / `ai_reports` | KEEP | 报告正文、模型和生成时输入快照 |
| `SystemConfigRecord` / `system_configs` | KEEP | 加密保存高德和 DeepSeek 配置 |

## 旧模型和冻结模型

### HIDE

- `site_scores`、动态 scoring config：MVP 不以复杂数字评分作为主要结论。
- `chat_sessions`：若保留报告后咨询，只作为辅助，不写回事实。
- `population_data`：不得把代理指标显示为真实人口。
- crawler、government stats、memory、business outcome、demo 相关模型。

### DELETE LATER

- `site_evaluations`、`candidate_sites`、`property_surveys`、`poi_observations`、旧 enrichment、旧 scoring/report 数据链。
- `crawl_tasks`、`crawler_field_suggestions`。
- `regional_statistics`、`data_sync_runs`。
- memory、business outcome 和不再使用的通用 Provider 登记。

删除必须在新流程稳定、生产数据备份、引用为零后通过独立 Alembic migration 完成。Phase A 不删除任何表。

## 字段真实性

业务字段需要两个正交标记：

- 值状态：`FACT` / `UNKNOWN`
- 来源：`AMAP_PROVIDED` / `USER_PROVIDED` / `CALCULATED` / `UNKNOWN`

高德原始响应可以保存在内部 `raw_data` 中用于映射审计，但普通 API、页面和 AI 快照只使用白名单字段。人工修正需要保留来源和修改历史，重新采集高德不得覆盖人工值。

Phase D 使用现有 JSON 与审计表实现人工覆盖层，不新增数据库字段：

- 业务记录的原始 `source` 保持不变，例如高德竞品人工补充后仍为 `amap`。
- 人工详情写入 `raw_data.manual_detail`，不改写高德原始字段。
- `raw_data._manual_meta.field_sources` 记录字段级来源，值为 `manual` 或 `manual_unknown`。
- `raw_data._manual_meta.unknown_fields` 保存用户明确标记的未知字段，并支持取消未知标记。
- `raw_data._manual_meta.verified_at` 保存最近人工核实时间。
- `raw_data._manual_meta.history` 保留最近 100 次字段变化摘要；完整审计继续写入 `manual_inputs`。
- 候选物业复用 `supplements`，使用 `target_type=candidate_property`、`target_id=primary`，避免创建重复业务表。

项目最近一次高德采集结论写入 `site_projects.raw_data._amap_collection`，用于区分：

- `not_started`：从未执行采集。
- `needs_confirmation`：地址存在多个候选，等待确认。
- `failed`：请求失败。
- `success_zero`：请求成功，但本次范围返回零条有效 POI。
- `partial`：部分关键词成功。
- `truncated`：成功但达到配置上限。
- `success`：成功。

该状态只记录采集结论、时间和数量摘要，不保存 Key 或敏感请求信息。

## AI 报告快照

Phase G 不新增数据库字段。`ai_reports.input_snapshot.final_project_snapshot` 保存生成时的
`final-project-snapshot-v1`，只包含白名单业务字段和字段级来源；`score_snapshot` 固定为空。
重新生成报告会创建新记录，历史快照保持不变。模型校验失败信息写入 `ai_call_logs`，状态为
`validation_failed`，不保存违规报告正文。

## 坐标

高德坐标保存并标记为 GCJ-02，不伪装为 WGS84。距离使用高德实际返回或由已知坐标执行的确定性计算，并标记 `CALCULATED`。
