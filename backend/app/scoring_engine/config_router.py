from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.scoring_engine.config_schemas import ScoringConfigResponse, ScoringConfigUpdate
from app.scoring_engine.config_service import list_scoring_config, replace_scoring_config, reset_scoring_config


router = APIRouter(prefix="/api/scoring", tags=["scoring-config"])


@router.get("/config", response_model=ScoringConfigResponse)
def get_scoring_config(db: Session = Depends(get_db)):
    return list_scoring_config(db)


@router.put("/config", response_model=ScoringConfigResponse)
def put_scoring_config(body: ScoringConfigUpdate, db: Session = Depends(get_db)):
    try:
        return replace_scoring_config(db, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/config/reset", response_model=ScoringConfigResponse)
def reset_scoring_config_api(db: Session = Depends(get_db)):
    return reset_scoring_config(db)
