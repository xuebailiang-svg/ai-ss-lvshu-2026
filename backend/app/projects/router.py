from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.projects.schemas import ProjectCreate, ProjectDataImport
from app.projects.service import (
    create_project,
    data_quality,
    dataset,
    get_project,
    import_project_data,
    list_projects,
    project_stats,
    project_to_dict,
    soft_delete_project,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def create_project_api(body: ProjectCreate, db: Session = Depends(get_db)):
    project = create_project(db, body)
    return {"project_id": project.project_id, "project": project_to_dict(project)}


@router.get("")
def list_projects_api(db: Session = Depends(get_db)):
    return {"items": [project_to_dict(project) for project in list_projects(db)]}


@router.get("/{project_id}")
def get_project_api(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return {"project": project_to_dict(project), "stats": project_stats(db, project.project_id)}


@router.delete("/{project_id}", status_code=204)
def delete_project_api(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    soft_delete_project(db, project)
    return Response(status_code=204)


@router.get("/{project_id}/dataset")
def project_dataset_api(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return dataset(db, project)


@router.post("/{project_id}/data/import")
def import_project_data_api(project_id: str, body: ProjectDataImport, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    row, warnings = import_project_data(db, project.project_id, body.type, body.data)
    return {"success": True, "type": body.type, "data": row, "warnings": warnings}


@router.get("/{project_id}/data-quality")
def project_data_quality_api(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return data_quality(db, project.project_id)
