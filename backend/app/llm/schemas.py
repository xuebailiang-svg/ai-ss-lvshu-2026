from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AIAnalysisInput(BaseModel):
    project: dict[str, Any]
    location: dict[str, Any]
    environment: dict[str, Any]
    competitors: list[dict[str, Any]]
    competitor_analysis: dict[str, Any] = Field(default_factory=dict)
    supporting_analysis: dict[str, Any] = Field(default_factory=dict)
    rent_analysis: dict[str, Any] = Field(default_factory=dict)
    city_insight: dict[str, Any] = Field(default_factory=dict)
    # 兼容既有输入结构；租金成本分析必须使用 rent_analysis。
    rent: dict[str, Any]
    score_result: dict[str, Any]
    data_quality: dict[str, Any]
    simulation_data_summary: dict[str, Any] = Field(default_factory=dict)
    memory_context: list[dict[str, Any]] = Field(default_factory=list)
    crawler_evidence_summary: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)


class AIReportResponse(BaseModel):
    success: bool = True
    report_id: str | None = None
    content: str | None = None
    model: str | None = None
    created_at: Any | None = None
    message: str | None = None
    snapshot_version: str | None = None
    validation_status: str | None = None


class AIReviewResponse(BaseModel):
    success: bool = True
    content: str | None = None
    model: str | None = None
    reviewed_at: Any | None = None
    data_quality: dict[str, Any] | None = None
    message: str | None = None


class DeepSeekResult(BaseModel):
    content: str
    model: str
    duration_ms: int
    input_length: int
    output_length: int


class AIQuestionOption(BaseModel):
    label: str
    value: str


class AIQuestion(BaseModel):
    question_id: str
    field_key: str
    target_type: str
    target_id: str
    title: str
    help_text: str | None = None
    answer_type: str
    unit: str | None = None
    options: list[AIQuestionOption] = Field(default_factory=list)
    round: int


class AIQuestionsRequest(BaseModel):
    continue_round: bool = False


class AIQuestionsResponse(BaseModel):
    success: bool = True
    status: str
    round: int
    questions: list[AIQuestion] = Field(default_factory=list)
    asked_count: int = 0
    remaining_candidate_count: int = 0
    message: str


class AIQuestionAnswer(BaseModel):
    question_id: str
    value: str | float | int | bool | None = None
    unknown: bool = False
    skip: bool = False


class AIQuestionAnswersRequest(BaseModel):
    answers: list[AIQuestionAnswer] = Field(min_length=1, max_length=3)


class AIQuestionAnswersResponse(BaseModel):
    success: bool = True
    saved_count: int
    unknown_count: int
    skipped_count: int
    can_continue: bool
    message: str
