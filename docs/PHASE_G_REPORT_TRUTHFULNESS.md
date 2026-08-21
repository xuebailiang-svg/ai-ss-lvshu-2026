# Phase G：AI 报告真实性重构实施说明

## 1. 实施结果

正式 AI 报告不再读取旧评分、政府宏观数据、Memory、爬虫证据、模拟数据或原始 `raw_data`，统一改为：

```text
高德事实 + 用户人工事实 + 明确未知 + 确定性计算
→ final_project_snapshot
→ DeepSeek 固定八章报告
→ 章节 / 结论 / 数字真实性校验
→ 校验通过后保存独立报告版本
```

旧 `build_ai_input` 暂时保留供兼容接口和历史测试使用，但 `/api/projects/{project_id}/ai-report` 已不再调用它。

## 2. 最终快照

新增 `backend/app/llm/snapshot.py`，快照版本为：

```text
final-project-snapshot-v1
```

允许来源只有：

- `AMAP_PROVIDED`：高德采集的地点、类别、地址和距离事实。
- `USER_PROVIDED`：用户通过人工补充或 Phase F 回答明确保存的事实。
- `CALCULATED`：由当前快照确定性计算的数量、准备度和半径换算。
- `UNKNOWN`：用户明确表示不知道或当前字段缺失。

明确排除：

- `score_result` 和旧复杂评分。
- `city_insight` 和政府统计。
- Memory。
- crawler 及爬虫证据。
- simulation / demo 数据。
- rejected 数据。
- `raw_data`、`confidence` 和内部调试字段。

高德疑似竞品和人工已确认竞品在快照中分开标记。竞品经营字段只有人工来源才会进入报告快照。

## 3. 固定报告结构

正式报告固定八章：

1. 项目概况
2. 核心结论
3. 交通环境
4. 竞争环境
5. 周边商业配套
6. 物业与租金
7. 数据缺失与风险
8. 最终建议

核心结论只允许：`推荐`、`谨慎`、`不推荐`、`数据不足`。

技术前置条件未完成时由后端直接生成八章“数据不足”报告，不调用大模型。关键物业或竞品信息不足时，快照会将 `allowed_conclusion` 固定为“数据不足”。

## 4. 输出真实性校验

新增 `backend/app/llm/report_validation.py`，发布前检查：

- 报告标题存在。
- 八个章节完整且顺序正确。
- 核心结论符合准备度守卫。
- 不包含禁止的推测表达。
- 报告正文中的每个阿拉伯数字都能在快照中找到，百分比只允许由快照中的比例确定性换算。

第一次校验失败时，系统把具体错误反馈给模型并自动重试一次。第二次仍失败时：

- 不保存报告正文。
- 返回“真实性校验失败，未发布”。
- 在 `ai_call_logs` 中保存 `validation_failed`，便于排查。

## 5. 报告版本

每次生成成功都会新增一条 `ai_reports` 记录：

- 不覆盖旧报告。
- `input_snapshot` 保存当次完整 `final_project_snapshot`。
- `score_snapshot` 固定为空，不再保存旧评分。
- API 返回 `snapshot_version` 和 `validation_status`。

后续修改项目不会改变历史报告的输入快照。

## 6. 前端变化

项目详情 Step 6：

- 校验通过后显示“真实性校验已通过”。
- 明确报告只读取高德事实、用户事实和确定性计算。
- 报告显示目录。
- 提供“打印 / PDF”入口。
- 两次校验失败时显示明确错误，不展示或保存违规报告。

HTML 导出按钮的位置和完整响应式报告布局留在 Phase H 统一处理。

## 7. 数据库变化

本阶段没有新增表、字段或 Alembic migration，复用现有：

- `ai_reports.input_snapshot`
- `ai_reports.report_content`
- `ai_call_logs.status/error_message`

## 8. 验证范围

- 快照白名单与禁用字段排除。
- 高德、人工、确定性计算和未知来源标签。
- crawler / rejected 数据不进入快照。
- 固定八章和结论守卫。
- 快照外数字触发重试并阻止发布。
- 第一次失败、第二次通过的重试链路。
- 每次生成创建新的不可变报告版本。
- 前端真实性提示、目录和打印入口。

最终验证结果：

- Phase G / LLM / Chat / Phase F / 准备度针对性测试：`41 passed`。
- 后端完整回归：`278 passed`。
- 前端测试：`9 passed`。
- 前端生产构建：成功。
- 构建存在 Ant Design vendor chunk 超过 500 kB 的既有警告，不影响本阶段构建结果。
