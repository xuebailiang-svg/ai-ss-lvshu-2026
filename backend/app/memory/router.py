from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.memory.schemas import (
    MemoryContextResponse,
    MemoryItemCreate,
    MemoryItemResponse,
    MemoryItemUpdate,
    MemoryListResponse,
    MemoryReviewRequest,
)
from app.memory.service import (
    create_memory_item,
    get_memory_item,
    list_memory_items,
    memory_to_dict,
    relevant_memory_context,
    review_memory_item,
    update_memory_item,
)
from app.projects.service import get_project


router = APIRouter(tags=["memory"])


@router.get("/api/memory", response_model=MemoryListResponse)
def list_memory_api(
    project_id: str | None = None,
    scope: str | None = None,
    memory_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    rows = list_memory_items(db, project_id=project_id, scope=scope, memory_type=memory_type, status=status)
    return {"items": [memory_to_dict(row) for row in rows], "total": len(rows)}


@router.post("/api/memory", response_model=MemoryItemResponse)
def create_memory_api(body: MemoryItemCreate, db: Session = Depends(get_db)):
    if body.scope == "project" and not body.project_id:
        raise HTTPException(400, "project scope memory requires project_id")
    return memory_to_dict(create_memory_item(db, body))


@router.put("/api/memory/{memory_id}", response_model=MemoryItemResponse)
def update_memory_api(memory_id: int, body: MemoryItemUpdate, db: Session = Depends(get_db)):
    row = get_memory_item(db, memory_id)
    if not row:
        raise HTTPException(404, "Memory item not found")
    return memory_to_dict(update_memory_item(db, row, body))


@router.post("/api/memory/{memory_id}/review", response_model=MemoryItemResponse)
def review_memory_api(memory_id: int, body: MemoryReviewRequest, db: Session = Depends(get_db)):
    row = get_memory_item(db, memory_id)
    if not row:
        raise HTTPException(404, "Memory item not found")
    try:
        return memory_to_dict(review_memory_item(db, row, body.status))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/api/memory/{memory_id}", status_code=204)
def delete_memory_api(memory_id: int, db: Session = Depends(get_db)):
    row = get_memory_item(db, memory_id)
    if not row:
        raise HTTPException(404, "Memory item not found")
    review_memory_item(db, row, "disabled")
    return Response(status_code=204)


@router.get("/api/projects/{project_id}/memory/context", response_model=MemoryContextResponse)
def project_memory_context_api(
    project_id: str,
    tags: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"project_id": project_id, "items": relevant_memory_context(db, project_id, tags=tags)}
