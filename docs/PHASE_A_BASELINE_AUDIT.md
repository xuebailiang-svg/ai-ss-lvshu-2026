# Phase A 当前代码基线审计

> 审计目标：确认收敛版 MVP 的唯一主链、冻结范围和发布阻塞项。本文不代表旧模块已删除。

## 1. 主链结论

继续使用：

```text
/api/projects
→ /api/projects/{id}/geocode
→ /api/projects/{id}/collect/amap
→ competitors / supporting / rent / manual-input
→ data-quality
→ ai-review（后续改为有限提问）
→ ai-report
```

核心表是 `site_projects`，不是 `projects`。服务器诊断和运维文档必须查询真实表名。

## 2. 后端路由审计

| 路由模块 | 分类 | Phase A 处理 |
|---|---|---|
| projects、map_data | KEEP | 唯一项目与高德主链 |
| competitor、supporting、rent、manual_input | SIMPLIFY | 后续围绕高德对象和候选物业收敛 |
| llm | SIMPLIFY | 后续只读最终快照 |
| system_config | SIMPLIFY | 后续只暴露高德和 DeepSeek |
| chat、scoring_engine、scoring config | HIDE | 停止新增功能 |
| crawler、government stats、memory、business outcome、demo | HIDE | 不进入 MVP 页面和 AI |
| `app.api.routes` 中旧 evaluation/agent/trace/debug | DELETE LATER | 先完成引用和数据迁移审计 |

当前 `backend/app/main.py` 仍注册所有模块。Phase A 不删除路由，Phase B 先隐藏前端入口，后续再停用 API。

## 3. 前端路由审计

当前主导航只显示工作台和配置，但 `frontend/src/App.tsx` 仍直接开放：

- 两套项目入口：`/` Workbench 与 `/projects/:projectId` ProjectDetail。
- `/legacy/*` 全套旧路由。
- `/agent`、`/evaluations/:id`、`/history`、`/reports/:id`。
- 项目 supplement、upload、chat 等独立页面。

Phase B 应统一为项目列表、创建、项目详情和配置四类页面，旧 URL 安全重定向。

## 4. 数据模型审计

- 新主链：`site_projects`、`pois`、`competitors`、`food_businesses`、`entertainments`、`rent_data`、`manual_inputs`、`ai_reports`。
- 旧主链：`site_evaluations`、`candidate_sites`、旧 POI/enrichment、旧 scoring/report。
- 扩展链：crawler、government statistics、memory、business outcome、dynamic scoring。

Phase A 不删表。分类和后续处理见 `docs/DATA_MODEL.md`。

## 5. 迁移审计

- 当前迁移为 0001–0015，逻辑上单链。
- 原 `0014_backfill_amap_business_hours` revision 长 33 字符，会超过 PostgreSQL 默认 `alembic_version.version_num VARCHAR(32)`。
- 线上曾手工使用 `0014_amap_hours`，Git 必须统一为短 ID。
- 安装升级前增加精确兼容：只把已知旧 ID `0014_backfill_amap_business_hours` 更新为 `0014_amap_hours`。
- 兼容程序不创建表、不 stamp、不猜测未知版本。

## 5.1 运行环境审计

- 当前锁定的 `SQLAlchemy 2.0.40` 不兼容 Python 3.14，项目元数据明确限制为 `Python >=3.10,<3.14`。
- Ubuntu 生产环境当前使用 Python 3.10，符合范围。
- Windows 开发建议使用 Python 3.11–3.13；不得用系统 Python 3.14 的新依赖版本通过测试后误认为锁定依赖同样兼容。
- Vitest `threads` pool 在当前 Windows 环境会在收集用例前挂起，发布测试改用单进程 `forks`，牺牲少量速度换取稳定性。

## 6. AI 与真实性审计

当前 AI 输入包含评分、城市洞察、Memory、爬虫证据和模拟摘要，与新 MVP 冲突。Phase G 前必须建立最终快照白名单；在此之前冻结相关 AI 扩展，不继续增加上下文。

当前 `ai-review` 是 Markdown 审核，不是结构化、有限轮次的问题机制；Phase F 重构。

## 7. Phase A 冻结清单

从本阶段开始停止继续维护新功能：

- crawler / Playwright Worker
- government stats / city insight
- memory / similar cases
- business outcome
- demo data
- complex agent / tools / trace / reflection
- dynamic scoring dimensions
- third-party provider expansion

只允许安全修复，且不得把上述数据重新带入 MVP 报告。

## 8. 进入 Phase B 的门槛

- 迁移 ID 兼容方案进入代码和安装链路。
- revision 长度、单 head、空库升级、历史 ID 兼容测试通过。
- 后端完整测试通过。
- 前端测试和构建通过。
- 文档明确唯一主链和冻结范围。
- 工作区没有密钥、数据库、日志或临时文件。

## 9. Phase A 验证记录（2026-08-12）

- Alembic 专项测试：4 passed，包括空库升级、无版本既有结构、revision 长度和旧长 ID 兼容。
- Alembic head：`0015_crawler_review_outcomes`，单一 head。
- 后端完整测试：251 passed。
- 前端测试：2 files、23 tests 全部通过。
- 前端生产构建：成功；保留现有 `antd`/`charts` 大 chunk 警告，不属于 Phase A 阻塞。
- Python 编译检查：迁移兼容模块与 0014/0015 migration 通过。
- 敏感信息扫描：未发现真实 Key、Token 或加密密钥；命中项均为配置占位说明或运维查询命令。
- `git diff --check`：通过，仅有 Windows 工作区 LF/CRLF 提示。

本机唯一环境限制：现有 `backend/.venv` 由 Python 3.14 创建，与锁定的 `SQLAlchemy 2.0.40`
不兼容。完整后端测试使用当前桌面兼容依赖执行；Ubuntu 生产 Python 3.10 属于正式支持范围。
下一次 Windows 创建虚拟环境必须使用 Python 3.11–3.13。
