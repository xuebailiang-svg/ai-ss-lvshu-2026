from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.business_outcome.schemas import BusinessOutcomeResponse, BusinessOutcomeReview, BusinessOutcomeUpsert
from app.business_outcome.service import BusinessOutcomeNotFoundError, get_outcome, review_outcome, upsert_outcome
from app.core.database import get_db


router = APIRouter(prefix="/api/projects", tags=["business-outcome"])


@router.get("/{project_id}/business-outcome", response_model=BusinessOutcomeResponse | None)
def get_project_business_outcome(project_id: str, db: Session = Depends(get_db)):
    try:
        return get_outcome(db, project_id)
    except BusinessOutcomeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.put("/{project_id}/business-outcome", response_model=BusinessOutcomeResponse)
def put_project_business_outcome(project_id: str, payload: BusinessOutcomeUpsert, db: Session = Depends(get_db)):
    try:
        return upsert_outcome(db, project_id, payload.model_dump())
    except BusinessOutcomeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{project_id}/business-outcome/review", response_model=BusinessOutcomeResponse)
def review_project_business_outcome(project_id: str, payload: BusinessOutcomeReview, db: Session = Depends(get_db)):
    try:
        return review_outcome(db, project_id, payload.status)
    except BusinessOutcomeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
