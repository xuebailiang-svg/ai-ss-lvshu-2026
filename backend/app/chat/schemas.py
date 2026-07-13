from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatSessionCreateResponse(BaseModel):
    session_id: str
    project_id: str
    title: str | None = None


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatMessageResponse(BaseModel):
    answer: str
    references: list[str] = Field(default_factory=list)
    simulation: dict[str, Any] | None = None


class ChatMessagesResponse(BaseModel):
    session_id: str
    project_id: str
    conversation_summary: str | None = None
    messages: list[dict[str, Any]]
