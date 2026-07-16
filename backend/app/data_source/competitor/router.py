from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db

from .schemas import (
    CompetitorCollectResponse,
    CompetitorListResponse,
    CompetitorListItem,
    CompetitorDetailUpdate,
    CompetitorReviewRequest,
)
from .service import (
    CompetitorNotFoundError,
    CompetitorProjectNotFoundError,
    collect_project_competitors,
    list_project_competitors,
    get_project_competitor,
    review_project_competitor,
    update_project_competitor_detail,
)


router = APIRouter(prefix="/api/projects", tags=["competitor-data"])


@router.post("/{project_id}/collect/competitors", response_model=CompetitorCollectResponse)
async def collect_project_competitors_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return await collect_project_competitors(db, project_id)
    except CompetitorProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.get("/{project_id}/competitors", response_model=CompetitorListResponse)
def list_project_competitors_api(project_id: str, db: Session = Depends(get_db)):
    try:
        items = list_project_competitors(db, project_id)
    except CompetitorProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    return {"items": items, "total": len(items)}


@router.post("/{project_id}/competitors/{competitor_id}/review")
def review_project_competitor_api(
    project_id: str,
    competitor_id: int,
    body: CompetitorReviewRequest,
    db: Session = Depends(get_db),
):
    try:
        return review_project_competitor(db, project_id, competitor_id, body.status)
    except CompetitorProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except CompetitorNotFoundError:
        raise HTTPException(status_code=404, detail="Competitor not found") from None


@router.get("/{project_id}/competitors/{competitor_id}", response_model=CompetitorListItem)
def get_project_competitor_api(
    project_id: str,
    competitor_id: int,
    db: Session = Depends(get_db),
):
    try:
        return get_project_competitor(db, project_id, competitor_id)
    except CompetitorProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except CompetitorNotFoundError:
        raise HTTPException(status_code=404, detail="Competitor not found") from None


@router.put("/{project_id}/competitors/{competitor_id}", response_model=CompetitorListItem)
def update_project_competitor_detail_api(
    project_id: str,
    competitor_id: int,
    body: CompetitorDetailUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_project_competitor_detail(
            db,
            project_id,
            competitor_id,
            body.model_dump(exclude_unset=True),
        )
    except CompetitorProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except CompetitorNotFoundError:
        raise HTTPException(status_code=404, detail="Competitor not found") from None
