from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.manual_input.schemas import ManualInputRequest, ManualInputResponse, ManualInputsResponse, MissingDataResponse
from app.manual_input.service import (
    ManualInputValidationError,
    ProjectNotFoundError,
    list_manual_inputs,
    missing_data,
    save_manual_input,
)

router = APIRouter(prefix="/api/projects", tags=["manual-input"])


@router.get("/{project_id}/missing-data", response_model=MissingDataResponse)
def project_missing_data_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return missing_data(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/manual-input", response_model=ManualInputResponse)
def project_manual_input_api(project_id: str, body: ManualInputRequest, db: Session = Depends(get_db)):
    try:
        return save_manual_input(db, project_id, body.type, body.target_id, body.data)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except ManualInputValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/manual-inputs", response_model=ManualInputsResponse)
def project_manual_inputs_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return {"project_id": project_id, "items": list_manual_inputs(db, project_id)}
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
