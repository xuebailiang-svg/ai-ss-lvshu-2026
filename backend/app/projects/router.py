from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.projects.schemas import ProjectCreate, ProjectDataImport
from app.projects.csv_upload import CsvUploadError, import_project_csv
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
    items = []
    for project in list_projects(db):
        item = project_to_dict(project)
        item["stats"] = project_stats(db, project.project_id)
        items.append(item)
    return {"items": items}


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


@router.post("/{project_id}/data/upload")
async def upload_project_data_api(
    project_id: str,
    data_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "仅支持CSV文件")

    max_bytes = 5 * 1024 * 1024
    try:
        content = await file.read(max_bytes + 1)
    finally:
        await file.close()
    if len(content) > max_bytes:
        raise HTTPException(413, "CSV文件不能超过5MB")
    try:
        return import_project_csv(db, project.project_id, data_type, content)
    except CsvUploadError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/{project_id}/data-quality")
def project_data_quality_api(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return data_quality(db, project.project_id)
