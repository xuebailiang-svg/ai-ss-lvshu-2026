from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.data_source.crawler.schemas import (
    CrawlEnrichRequest,
    CrawlEnrichResponse,
    CrawlTaskDetailResponse,
    CrawlTaskListResponse,
)
from app.data_source.crawler.service import (
    CrawlProjectNotFoundError,
    CrawlTaskNotFoundError,
    enrich_project_with_crawler,
    get_crawl_task,
    list_crawl_tasks,
)


router = APIRouter(prefix="/api/projects", tags=["crawler-data"])


@router.post("/{project_id}/crawl/enrich", response_model=CrawlEnrichResponse)
async def crawl_enrich_project(
    project_id: str,
    payload: CrawlEnrichRequest,
    db: Session = Depends(get_db),
) -> CrawlEnrichResponse:
    try:
        result = await enrich_project_with_crawler(
            db,
            project_id=project_id,
            types=list(payload.types),
            max_items=payload.max_items,
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
