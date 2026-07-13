from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm.service import latest_score
from app.models import AIReportRecord, ChatMessageRecord, ChatSessionRecord
from app.projects.service import dataset, get_project, row_to_dict


MAX_HISTORY_MESSAGES = 40


class ChatContextError(RuntimeError):
    pass


def latest_report(db: Session, project_id: str) -> dict[str, Any]:
    row = db.scalar(
        select(AIReportRecord)
        .where(AIReportRecord.project_id == project_id)
        .order_by(AIReportRecord.created_at.desc(), AIReportRecord.id.desc())
    )
    if not row:
        return {}
    return {
        "report_id": row.id,
        "content": row.report_content,
        "model": row.model_name,
        "created_at": row.created_at,
    }


def recent_messages(db: Session, session_id: int, limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == session_id)
        .order_by(ChatMessageRecord.created_at.desc(), ChatMessageRecord.id.desc())
        .limit(limit)
    ).all()
    return [row_to_dict(row) for row in reversed(rows)]


def build_project_chat_context(db: Session, session: ChatSessionRecord, user_message: str) -> dict[str, Any]:
    project = get_project(db, session.project_id)
    if not project:
        raise ChatContextError("Project not found")
    project_dataset = dataset(db, project)
    score = latest_score(db, session.project_id) or {}
    report = latest_report(db, session.project_id)
    history = recent_messages(db, session.id)
    context = {
        "project": project_dataset.get("project", {}),
        "dataset": project_dataset,
        "score": score,
        "latest_report": report,
        "conversation_summary": session.conversation_summary,
        "chat_history": [
            {"role": item.get("role"), "content": item.get("content")}
            for item in history
        ],
        "user_message": user_message,
    }
    simulation = detect_rent_simulation(user_message, score)
    if simulation:
        context["simulation"] = simulation
    return json.loads(json.dumps(context, ensure_ascii=False, default=str))


def detect_rent_simulation(message: str, score: dict[str, Any]) -> dict[str, Any] | None:
    text = message or ""
    if "租金" not in text or not any(word in text for word in ("降低", "下降", "减少", "便宜")):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    percent = float(match.group(1)) if match else 30.0
    original_score = float(score.get("total_score") or 0)
    rent_dimension = (score.get("dimensions") or {}).get("rent") or {}
    current_rent_score = float(rent_dimension.get("score") or 0)
    max_rent_score = float(rent_dimension.get("max") or 10)
    lift = min(max_rent_score - current_rent_score, max_rent_score * min(percent, 50) / 100)
    simulation_score = round(original_score + max(0, lift), 2)
    return {
        "simulation": True,
        "type": "rent_reduction",
        "rent_reduction_percent": percent,
        "original_score": original_score,
        "simulation_score": simulation_score,
        "changes": ["成本因素提升"] if simulation_score > original_score else ["当前租金维度已接近满分，降低租金对总分影响有限"],
        "notice": "这是临时模拟分析，不会修改真实项目数据。",
    }


def summarize_if_needed(db: Session, session: ChatSessionRecord) -> None:
    total = db.scalar(
        select(func.count()).select_from(ChatMessageRecord).where(ChatMessageRecord.session_id == session.id)
    )
    if not total or total <= MAX_HISTORY_MESSAGES:
        return
    older_rows = db.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == session.id)
        .order_by(ChatMessageRecord.created_at.asc(), ChatMessageRecord.id.asc())
        .limit(max(0, int(total) - MAX_HISTORY_MESSAGES))
    ).all()
    if not older_rows:
        return
    snippets = [f"{row.role}: {row.content[:120]}" for row in older_rows[-10:]]
    prefix = session.conversation_summary or "历史对话摘要："
    session.conversation_summary = (prefix + "\n" + "\n".join(snippets))[-3000:]
