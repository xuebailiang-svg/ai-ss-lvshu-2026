from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.llm.schemas import AIReportResponse
from app.llm.service import ProjectNotFoundError, generate_ai_report

router = APIRouter(prefix="/api/projects", tags=["llm"])


@router.post("/{project_id}/ai-report", response_model=AIReportResponse)
def generate_project_ai_report_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return generate_ai_report(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
