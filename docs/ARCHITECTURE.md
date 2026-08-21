# 架构基线

## 当前技术架构

系统是模块化单体：React + Ant Design 前端由 Nginx 托管，FastAPI 提供 API，SQLAlchemy/Alembic 管理 PostgreSQL/PostGIS。生产只公开 Nginx，后端监听 `127.0.0.1:8000`。

当前仓库已经演进出多条并行能力：高德采集、人工输入、评分、AI 报告、聊天、爬虫、政府数据、Memory、经营结果、Agent/Trace 等。它们仍共享同一 FastAPI 应用和数据库，不是独立微服务。

## MVP 唯一主链

经产品范围重新确认，后续唯一继续演进的主链为：

```text
site_projects
  → 高德地理编码与 POI 采集
  → pois / competitors / food_businesses / entertainments
  → 人工补充候选物业、租金和业务详情
  → 数据检查
  → AI 有限提问
  → final_project_snapshot
  → ai_reports
```

产品边界见 `docs/PRD_AMAP_MANUAL_AI_MVP.md`，实施顺序见 `docs/IMPLEMENTATION_PLAN_AMAP_MANUAL_AI_MVP.md`。

## 冻结的非 MVP 能力

以下模块当前可能仍被 FastAPI 注册或保留数据库表，但从 Phase A 起停止新增功能，后续先隐藏、再根据依赖和数据备份决定删除：

- crawler 与独立 Worker
- government statistics / city insight
- memory / business outcome
- demo data
- 动态 scoring config 与复杂评分展示
- Agent、Tool、Trace、Reflection、Feedback 调试链路
- 旧 `site_evaluations` 项目/报告链路

它们不得进入收敛版 MVP 的 AI 最终快照。

## 数据真实性边界

- 自动外部数据只允许高德 Web Service 实际响应。
- 人工值与高德值分层保存，不能互相覆盖。
- 确定性统计可进入报告；AI 不生成业务数值。
- `UNKNOWN` 是合法状态，不能被推测为事实。
- `raw_data`、`confidence`、Provider 状态和工具日志只用于内部排错，不展示给普通用户，也不发送给 AI。

正式报告由 `backend/app/llm/snapshot.py` 构建唯一 `final-project-snapshot-v1`，并由
`backend/app/llm/report_validation.py` 在保存前校验固定章节、允许结论和数字来源。首次校验失败仅重试一次；
再次失败不发布报告。每次成功生成都新增 `ai_reports` 记录，不覆盖历史快照。

## 发布与迁移

- 生产数据库只使用 Alembic 迁移，应用启动不代替迁移。
- Alembic revision 必须唯一且不超过默认 `version_num VARCHAR(32)`。
- 安装脚本在 `alembic upgrade head` 前运行精确的历史 revision 兼容检查，不自动 stamp 未知数据库。
- 空库、已有无版本表结构和生产版本升级都必须有自动化验证。
