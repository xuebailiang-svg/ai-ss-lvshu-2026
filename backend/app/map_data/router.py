from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.map_data.schemas import AmapCollectResponse
from app.map_data.service import (
    ProjectNotFoundError,
    collect_amap_for_project,
    geocode_project,
    record_amap_collection_result,
)

router = APIRouter(prefix="/api/projects", tags=["map-data"])


@router.post("/{project_id}/geocode")
async def geocode_project_api(
    project_id: str,
    force: bool = False,
    candidate_index: int | None = None,
    db: Session = Depends(get_db),
):
    try:
        return await geocode_project(db, project_id, force=force, candidate_index=candidate_index)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/collect/amap", response_model=AmapCollectResponse)
async def collect_project_amap_api(project_id: str, db: Session = Depends(get_db)):
    try:
        result = await collect_amap_for_project(db, project_id)
        record_amap_collection_result(db, project_id, result)
        return result
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
