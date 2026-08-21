from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.llm.questions import QuestionProjectNotFoundError, QuestionValidationError, generate_questions, save_answers
from app.llm.schemas import (
    AIQuestionAnswersRequest,
    AIQuestionAnswersResponse,
    AIQuestionsRequest,
    AIQuestionsResponse,
    AIReportResponse,
    AIReviewResponse,
)
from app.llm.service import ProjectNotFoundError, generate_ai_data_review, generate_ai_report

router = APIRouter(prefix="/api/projects", tags=["llm"])


@router.post("/{project_id}/ai-report", response_model=AIReportResponse)
def generate_project_ai_report_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return generate_ai_report(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/ai-review", response_model=AIReviewResponse)
def generate_project_ai_review_api(project_id: str, db: Session = Depends(get_db)):
    try:
        return generate_ai_data_review(db, project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/ai-questions", response_model=AIQuestionsResponse)
def generate_project_ai_questions_api(
    project_id: str,
    body: AIQuestionsRequest,
    db: Session = Depends(get_db),
):
    try:
        return generate_questions(db, project_id, continue_round=body.continue_round)
    except QuestionProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("/{project_id}/ai-questions/answers", response_model=AIQuestionAnswersResponse)
def save_project_ai_question_answers_api(
    project_id: str,
    body: AIQuestionAnswersRequest,
    db: Session = Depends(get_db),
):
    try:
        return save_answers(db, project_id, [item.model_dump() for item in body.answers])
    except QuestionProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found") from None
    except QuestionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
