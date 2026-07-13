from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.scoring_engine.schemas import ProjectScoreResponse
from app.scoring_engine.service import ProjectNotFoundError, score_project

router = APIRouter(prefix="/api/projects", tags=["scoring-engine"])


@router.post("/{project_id}/score", response_model=ProjectScoreResponse)
def score_project_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return score_project(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
