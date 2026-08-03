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
    CrawlerFieldSuggestionItem,
    CrawlerFieldSuggestionList,
    CrawlerSuggestionReviewRequest,
)
from app.data_source.crawler.service import (
    CrawlProjectNotFoundError,
    CrawlTaskNotFoundError,
    get_crawl_task,
    list_crawl_tasks,
    queue_manual_url_crawl_task,
    queue_project_crawler_tasks,
)
from app.data_source.crawler.review_service import (
    CrawlerSuggestionNotFoundError,
    list_suggestions,
    retry_task,
    review_suggestion,
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
            planning_mode=payload.planning_mode,
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


@router.post("/{project_id}/crawl/tasks/{task_id}/retry", response_model=CrawlEnrichResponse)
def retry_project_crawl_task(project_id: str, task_id: int, db: Session = Depends(get_db)) -> CrawlEnrichResponse:
    try:
        task = retry_task(db, project_id, task_id)
        return CrawlEnrichResponse(
            success=True, project_id=project_id, task_count=1, task_ids=[task.id],
            completed_count=0, failed_count=0, skipped_count=0, discovered_url_count=0,
            saved={"competitors": 0, "supporting": 0, "rent": 0},
            message="重试任务已创建，独立 Worker 将在后台处理",
        )
    except CrawlerSuggestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{project_id}/crawler-suggestions", response_model=CrawlerFieldSuggestionList)
def get_project_crawler_suggestions(
    project_id: str,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> CrawlerFieldSuggestionList:
    try:
        return CrawlerFieldSuggestionList(**list_suggestions(db, project_id, status))
    except CrawlerSuggestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{project_id}/crawler-suggestions/{suggestion_id}/review", response_model=CrawlerFieldSuggestionItem)
def review_project_crawler_suggestion(
    project_id: str,
    suggestion_id: int,
    payload: CrawlerSuggestionReviewRequest,
    db: Session = Depends(get_db),
) -> CrawlerFieldSuggestionItem:
    try:
        return CrawlerFieldSuggestionItem(**review_suggestion(
            db, project_id, suggestion_id, action=payload.action,
            final_value=payload.final_value, remark=payload.remark,
        ))
    except CrawlerSuggestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
