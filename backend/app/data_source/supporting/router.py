from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db

from .schemas import (
    SupportingCollectResponse,
    SupportingDetailResponse,
    SupportingDetailUpdate,
    SupportingListResponse,
    SupportingListItem,
    SupportingReviewRequest,
)
from .service import (
    SupportingDetailValidationError,
    SupportingItemNotFoundError,
    SupportingItemNotConfirmedError,
    SupportingProjectNotFoundError,
    collect_project_supporting,
    get_project_supporting_detail,
    list_project_supporting,
    review_project_supporting,
    update_project_supporting_detail,
)


router = APIRouter(prefix="/api/projects", tags=["supporting-data"])


@router.post("/{project_id}/collect/supporting", response_model=SupportingCollectResponse)
async def collect_project_supporting_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return await collect_project_supporting(db, project_id)
    except SupportingProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.get("/{project_id}/supporting", response_model=SupportingListResponse)
def list_project_supporting_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return list_project_supporting(db, project_id)
    except SupportingProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/supporting/{supporting_id}/review", response_model=SupportingListItem)
def review_project_supporting_api(
    project_id: str,
    supporting_id: str,
    body: SupportingReviewRequest,
    db: Session = Depends(get_db),
):
    try:
        return review_project_supporting(db, project_id, supporting_id, body.status)
    except SupportingProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except SupportingItemNotFoundError:
        raise HTTPException(status_code=404, detail="Supporting item not found") from None


@router.get("/{project_id}/supporting/{supporting_id}", response_model=SupportingDetailResponse)
def get_project_supporting_detail_api(
    project_id: str,
    supporting_id: str,
    db: Session = Depends(get_db),
):
    try:
        return get_project_supporting_detail(db, project_id, supporting_id)
    except SupportingProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except SupportingItemNotFoundError:
        raise HTTPException(status_code=404, detail="Supporting item not found") from None


@router.put("/{project_id}/supporting/{supporting_id}", response_model=SupportingDetailResponse)
def update_project_supporting_detail_api(
    project_id: str,
    supporting_id: str,
    body: SupportingDetailUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_project_supporting_detail(
            db,
            project_id,
            supporting_id,
            body.model_dump(exclude_unset=True),
        )
    except SupportingProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except SupportingItemNotFoundError:
        raise HTTPException(status_code=404, detail="Supporting item not found") from None
    except SupportingItemNotConfirmedError:
        raise HTTPException(status_code=409, detail="请先确认该配套信息，再补充经营详情") from None
    except SupportingDetailValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
