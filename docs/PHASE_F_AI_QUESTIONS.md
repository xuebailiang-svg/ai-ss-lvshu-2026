# Phase F：AI 重要信息提问实施说明

## 1. 实施结果

Phase F 已将原来的 Markdown 数据审核收敛为受控的结构化重要问题流程：

```text
确定性缺失字段目录
→ DeepSeek 只选择 candidate_id
→ 后端再次校验
→ 用户填写 / 不知道 / 暂不提供
→ 写回对应业务字段和人工审计记录
```

旧 `/ai-review` 仅保留兼容，不再作为六步工作台中的用户流程。

## 2. 提问边界

- 默认一轮，最多两轮。
- 每轮最多 3 题，总计最多 5 题。
- 只允许询问系统目录中的候选物业和重点竞品字段。
- 已有值、已问字段以及已标记“不知道”的字段不会重复询问。
- 禁止询问或推测人口、客流、消费能力、营业额、利润、回本和预测数据。
- DeepSeek 只返回被选择的 `candidate_id`；问题标题、说明、单位和输入类型全部由后端固定生成。
- 模型未配置、网络失败、超时、非法 JSON 或越界字段均安全降级为跳过，不阻塞报告。

## 3. 用户回答与来源

每个问题支持：

- 填写实际值：保存为 `user_provided`，并通过人工审计机制记录字段来源和变更历史。
- 不知道：写入字段级 `unknown_fields`，后续不再追问，不生成虚构值。
- 暂不提供：记录为跳过，不写入业务事实，后续不重复询问。

高德字段与用户补充仍分层保存；本阶段不会把 AI 输出直接写入业务字段。

## 4. API

### 生成问题

```http
POST /api/projects/{project_id}/ai-questions
Content-Type: application/json

{"continue_round": false}
```

第二轮仅在用户明确点击“继续第二轮（可选）”后请求：

```json
{"continue_round": true}
```

### 保存回答

```http
POST /api/projects/{project_id}/ai-questions/answers
Content-Type: application/json
```

```json
{
  "answers": [
    {"question_id": "q_xxx", "value": 500},
    {"question_id": "q_yyy", "unknown": true},
    {"question_id": "q_zzz", "skip": true}
  ]
}
```

## 5. 前端

项目详情 Step 5 新增结构化表单：

- 显示 AI 从允许目录中选择的问题。
- 根据字段类型显示文字、数字、金额、百分比、布尔或单选输入。
- 明确提供“不知道”和“暂不提供”。
- 保存成功后刷新 Step 4 数据准备度。
- 第一轮完成且仍有候选字段时，用户可以选择继续第二轮。

## 6. 数据库变化

本阶段没有新增表或字段，也没有新增 Alembic migration。

问题和回答状态复用 `supplement_records`：

- `target_type=ai_question`
- 初始来源 `ai_selected`
- 用户回答后来源 `user_provided`
- 用户跳过后来源 `user_skipped`

实际业务值继续写入现有竞品或候选物业记录，并产生人工变更审计。

## 7. 验证结果

- 后端 Phase F/LLM/准备度针对性测试：`28 passed`。
- 后端完整回归：`272 passed`。
- 前端测试：`8 passed`。
- 前端生产构建：成功。
- 构建仍有 Ant Design vendor chunk 超过 500 kB 的既有警告，不阻塞本阶段发布。
