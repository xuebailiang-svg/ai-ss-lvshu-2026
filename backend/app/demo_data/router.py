from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.demo_data.schemas import DemoDataGenerateRequest, DemoDataGenerateResponse
from app.demo_data.service import generate_project_demo_data
from app.projects.service import get_project

router = APIRouter(prefix="/api/projects", tags=["demo-data"])


@router.post("/{project_id}/demo-data/generate", response_model=DemoDataGenerateResponse)
def generate_project_demo_data_api(
    project_id: str,
    body: DemoDataGenerateRequest,
    db: Session = Depends(get_db),
):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return generate_project_demo_data(
        db,
        project,
        include=body.include,
        max_competitors=body.max_competitors,
        max_supporting=body.max_supporting,
        rent_samples=body.rent_samples,
    )
