from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db

from .schemas import (
    RentDetailResponse,
    RentDetailUpdate,
    RentImportResponse,
    RentListItem,
    RentListResponse,
    RentReviewRequest,
)
from .service import (
    RentCsvImportError,
    RentProjectNotFoundError,
    RentRecordNotFoundError,
    get_project_rent_detail,
    import_project_rent_csv,
    list_project_rent,
    review_project_rent,
    update_project_rent_detail,
)


router = APIRouter(prefix="/api/projects", tags=["rent-data"])


@router.post("/{project_id}/rent/import", response_model=RentImportResponse)
async def import_project_rent_csv_api(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持CSV文件")
    max_bytes = 5 * 1024 * 1024
    try:
        content = await file.read(max_bytes + 1)
    finally:
        await file.close()
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="CSV文件不能超过5MB")
    try:
        return await import_project_rent_csv(db, project_id, content)
    except RentProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except RentCsvImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/{project_id}/rent", response_model=RentListResponse)
def list_project_rent_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return list_project_rent(db, project_id)
    except RentProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/rent/{rent_id}/review", response_model=RentListItem)
def review_project_rent_api(
    project_id: str,
    rent_id: int,
    body: RentReviewRequest,
    db: Session = Depends(get_db),
):
    try:
        return review_project_rent(db, project_id, rent_id, body.status)
    except RentProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except RentRecordNotFoundError:
        raise HTTPException(status_code=404, detail="Rent record not found") from None


@router.get("/{project_id}/rent/{rent_id}", response_model=RentDetailResponse)
def get_project_rent_detail_api(project_id: str, rent_id: int, db: Session = Depends(get_db)):
    try:
        return get_project_rent_detail(db, project_id, rent_id)
    except RentProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except RentRecordNotFoundError:
        raise HTTPException(status_code=404, detail="Rent record not found") from None


@router.put("/{project_id}/rent/{rent_id}", response_model=RentDetailResponse)
def update_project_rent_detail_api(
    project_id: str,
    rent_id: int,
    body: RentDetailUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_project_rent_detail(db, project_id, rent_id, body.model_dump(exclude_unset=True))
    except RentProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except RentRecordNotFoundError:
        raise HTTPException(status_code=404, detail="Rent record not found") from None
