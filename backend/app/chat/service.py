from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.chat.context import build_project_chat_context, summarize_if_needed
from app.chat.prompts import CHAT_PROMPT
from app.llm.client import DeepSeekClient, DeepSeekConfigError
from app.models import ChatMessageRecord, ChatSessionRecord
from app.projects.service import get_project, row_to_dict


class ProjectNotFoundError(RuntimeError):
    pass


class ChatSessionNotFoundError(RuntimeError):
    pass


def create_chat_session(db: Session, project_id: str) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    session = ChatSessionRecord(
        project_id=project_id,
        title=f"{project.project_name or project.address} 咨询",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": str(session.id), "project_id": project_id, "title": session.title}


def get_chat_session(db: Session, session_id: str | int) -> ChatSessionRecord | None:
    if not str(session_id).isdigit():
        return None
    return db.get(ChatSessionRecord, int(session_id))


def send_chat_message(
    db: Session,
    session_id: str,
    message: str,
    *,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    session = get_chat_session(db, session_id)
    if not session:
        raise ChatSessionNotFoundError("Chat session not found")
    deepseek = client or DeepSeekClient()
    try:
        deepseek.ensure_configured()
    except DeepSeekConfigError:
        return {"answer": "DeepSeek API Key未配置", "references": [], "simulation": None}

    user_row = ChatMessageRecord(
        session_id=session.id,
        role="user",
        content=message,
        references=[],
        created_at=datetime.now(timezone.utc),
    )
    db.add(user_row)
    db.flush()
    context = build_project_chat_context(db, session, message)
    result = deepseek.generate_chat(context, CHAT_PROMPT)
    references = infer_references(context, message)
    simulation = context.get("simulation")
    assistant_row = ChatMessageRecord(
        session_id=session.id,
        role="assistant",
        content=result.content,
        references=references,
        simulation=simulation,
        created_at=datetime.now(timezone.utc),
    )
    db.add(assistant_row)
    session.updated_at = datetime.now(timezone.utc)
    summarize_if_needed(db, session)
    db.commit()
    return {"answer": result.content, "references": references, "simulation": simulation}


def list_chat_messages(db: Session, session_id: str) -> dict[str, Any]:
    session = get_chat_session(db, session_id)
    if not session:
        raise ChatSessionNotFoundError("Chat session not found")
    rows = db.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == session.id)
        .order_by(ChatMessageRecord.created_at.asc(), ChatMessageRecord.id.asc())
    ).all()
    return {
        "session_id": str(session.id),
        "project_id": session.project_id,
        "conversation_summary": session.conversation_summary,
        "messages": [row_to_dict(row) for row in rows],
    }


def infer_references(context: dict[str, Any], message: str) -> list[str]:
    refs = ["project"]
    text = message or ""
    if context.get("score"):
        refs.append("score_result")
    if "竞品" in text or context.get("dataset", {}).get("competitors"):
        refs.append("competitor_data")
    if "租金" in text or context.get("dataset", {}).get("rent_data"):
        refs.append("rent_data")
    if "报告" in text and context.get("latest_report"):
        refs.append("latest_report")
    if context.get("simulation"):
        refs.append("simulation")
    return refs
