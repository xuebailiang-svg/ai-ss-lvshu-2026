from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.chat.schemas import ChatMessageRequest, ChatMessageResponse, ChatMessagesResponse, ChatSessionCreateResponse
from app.chat.service import ChatSessionNotFoundError, ProjectNotFoundError, create_chat_session, list_chat_messages, send_chat_message
from app.core.database import get_db

router = APIRouter(tags=["chat"])


@router.post("/api/projects/{project_id}/chat/session", response_model=ChatSessionCreateResponse)
def create_project_chat_session_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return create_chat_session(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/api/chat/{session_id}/message", response_model=ChatMessageResponse)
def send_chat_message_api(session_id: str, body: ChatMessageRequest, db: Session = Depends(get_db)):
    try:
        return send_chat_message(db, session_id, body.message)
    except ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found") from None


@router.get("/api/chat/{session_id}/messages", response_model=ChatMessagesResponse)
def list_chat_messages_api(session_id: str, db: Session = Depends(get_db)):
    try:
        return list_chat_messages(db, session_id)
    except ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found") from None
