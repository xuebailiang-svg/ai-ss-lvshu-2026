# 项目 AI 聊天助手

本模块支持用户围绕一个选址项目持续向 AI 提问。

核心原则：

- 聊天必须加载项目上下文：项目、dataset、评分、最新 AI 报告、最近聊天历史。
- 只发送最近 40 条消息，约 20 轮对话。
- 超过历史限制后写入 `conversation_summary`，避免无限发送历史。
- “如果租金降低”等问题只做临时模拟分析，不修改真实项目数据。
- 不修改 Agent、评分模型和报告生成流程。

接口：

```http
POST /api/projects/{project_id}/chat/session
POST /api/chat/{session_id}/message
GET /api/chat/{session_id}/messages
```
