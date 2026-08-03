from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.map_data.schemas import AmapCollectResponse
from app.map_data.service import (
    ProjectNotFoundError,
    collect_amap_for_project,
    geocode_project,
)

router = APIRouter(prefix="/api/projects", tags=["map-data"])


@router.post("/{project_id}/geocode")
async def geocode_project_api(project_id: str, force: bool = False, db: Session = Depends(get_db)):
    try:
        return await geocode_project(db, project_id, force=force)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/collect/amap", response_model=AmapCollectResponse)
async def collect_project_amap_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return await collect_amap_for_project(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
