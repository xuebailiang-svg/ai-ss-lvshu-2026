from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.projects.service import get_project
from app.system_config.router import require_admin

from .schemas import GovernmentStatisticReview, GovernmentStatsSyncRequest
from .service import (
    city_insight,
    create_sync_run,
    execute_sync_run,
    has_fresh_cache,
    review_record,
    review_records,
    save_uploaded_statistics,
    sync_run_to_dict,
)
from .upload import GovernmentUploadAdapter


router = APIRouter(tags=["government-stats"])


@router.post("/api/projects/{project_id}/collect/government-stats")
def collect_project_government_stats(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if has_fresh_cache(db, project.city, project.district):
        insight = city_insight(db, project)
        return {
            "success": True,
            "status": "ready",
            "scope": {"city": project.city, "district": project.district},
            "confirmed_metric_count": insight["data_quality"]["confirmed_metric_count"],
            "pending_review_count": 0,
            "latest_period": insight["data_quality"]["latest_period"],
            "sources": sorted({item["source_name"] for item in insight["sources"]}),
            "message": "已使用本地缓存的政府公开数据",
        }
    run = create_sync_run(
        db,
        project_id=project.project_id,
        city=project.city,
        district=project.district,
        sources=["national", "shaanxi", "xian"],
    )
    background_tasks.add_task(execute_sync_run, run.id)
    return {
        "success": True,
        "status": "collecting",
        "run_id": run.id,
        "scope": {"city": project.city, "district": project.district},
        "confirmed_metric_count": 0,
        "pending_review_count": 0,
        "latest_period": None,
        "sources": [],
        "message": "政府公开数据同步任务已创建",
    }


@router.get("/api/projects/{project_id}/city-insight")
def get_project_city_insight(project_id: str, db: Session = Depends(get_db)):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return city_insight(db, project)


@router.post("/api/system/government-stats/sync", dependencies=[Depends(require_admin)])
def force_government_stats_sync(
    body: GovernmentStatsSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run = create_sync_run(
        db,
        project_id=None,
        city=body.city,
        district=body.district,
        sources=body.sources,
        force_refresh=True,
    )
    background_tasks.add_task(execute_sync_run, run.id)
    return {"success": True, "run": sync_run_to_dict(run), "message": "强制同步任务已创建"}


@router.get("/api/system/government-stats/review", dependencies=[Depends(require_admin)])
def list_government_stats_review(status: str = "pending_review", db: Session = Depends(get_db)):
    if status not in {"confirmed", "pending_review", "rejected"}:
        raise HTTPException(400, "Invalid review status")
    items = review_records(db, status)
    return {"items": items, "total": len(items)}


@router.post("/api/system/government-stats/{record_id}/review", dependencies=[Depends(require_admin)])
def review_government_statistic(
    record_id: int,
    body: GovernmentStatisticReview,
    db: Session = Depends(get_db),
):
    item = review_record(db, record_id, body.status)
    if not item:
        raise HTTPException(404, "Government statistic not found")
    return item


@router.post("/api/system/government-stats/upload", dependencies=[Depends(require_admin)])
async def upload_government_statistics(
    file: UploadFile = File(...),
    source_name: str = Form(...),
    source_url: str = Form(...),
    scope_level: str = Form("city"),
    scope_code: str = Form("610100"),
    scope_name: str = Form("西安市"),
    stat_period: str = Form(""),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx", ".pdf")):
        raise HTTPException(400, "仅支持 CSV、XLSX 或 PDF 文件")
    content = await file.read(20 * 1024 * 1024 + 1)
    await file.close()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "政府数据文件不能超过20MB")
    try:
        items, errors = GovernmentUploadAdapter().parse(
            filename,
            content,
            source_name=source_name,
            source_url=source_url,
            scope_level=scope_level,
            scope_code=scope_code,
            scope_name=scope_name,
            stat_period=stat_period,
        )
    except (UnicodeDecodeError, ValueError, RuntimeError) as exc:
        raise HTTPException(400, f"文件解析失败：{exc}") from exc
    stats = save_uploaded_statistics(db, items)
    return {
        "success": bool(items),
        **stats,
        "failed_count": len(errors),
        "errors": errors[:50],
        "message": "政府数据文件已导入；PDF抽取结果需要管理员确认" if items else "未导入任何指标",
    }
