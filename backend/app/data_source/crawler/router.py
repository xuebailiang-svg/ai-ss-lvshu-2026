from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.data_source.crawler.schemas import (
    CrawlEnrichRequest,
    CrawlEnrichResponse,
    CrawlManualUrlRequest,
    CrawlTaskDetailResponse,
    CrawlTaskListResponse,
)
from app.data_source.crawler.service import (
    CrawlProjectNotFoundError,
    CrawlTaskNotFoundError,
    get_crawl_task,
    list_crawl_tasks,
    queue_manual_url_crawl_task,
    queue_project_crawler_tasks,
)


router = APIRouter(prefix="/api/projects", tags=["crawler-data"])


@router.post("/{project_id}/crawl/enrich", response_model=CrawlEnrichResponse)
def crawl_enrich_project(
    project_id: str,
    payload: CrawlEnrichRequest,
    db: Session = Depends(get_db),
) -> CrawlEnrichResponse:
    try:
        result = queue_project_crawler_tasks(
            db,
            project_id=project_id,
            types=list(payload.types),
            max_items=payload.max_items,
            discover_urls=payload.discover_urls,
        )
        return CrawlEnrichResponse(**result)
    except CrawlProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/crawl/manual-url", response_model=CrawlEnrichResponse)
def crawl_manual_url_project(
    project_id: str,
    payload: CrawlManualUrlRequest,
    db: Session = Depends(get_db),
) -> CrawlEnrichResponse:
    try:
        result = queue_manual_url_crawl_task(
            db,
            project_id=project_id,
            task_type=payload.task_type,
            name=payload.name,
            address=payload.address,
            url=payload.url,
            record_type=payload.record_type,
        )
        return CrawlEnrichResponse(**result)
    except CrawlProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.get("/{project_id}/crawl/tasks", response_model=CrawlTaskListResponse)
def get_project_crawl_tasks(project_id: str, db: Session = Depends(get_db)) -> CrawlTaskListResponse:
    try:
        return CrawlTaskListResponse(**list_crawl_tasks(db, project_id))
    except CrawlProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.get("/{project_id}/crawl/tasks/{task_id}", response_model=CrawlTaskDetailResponse)
def get_project_crawl_task(project_id: str, task_id: int, db: Session = Depends(get_db)) -> CrawlTaskDetailResponse:
    try:
        return CrawlTaskDetailResponse(**get_crawl_task(db, project_id, task_id))
    except CrawlProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except CrawlTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Crawl task not found") from None
