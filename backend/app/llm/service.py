from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import DeepSeekClient, DeepSeekConfigError
from app.llm.schemas import AIAnalysisInput
from app.models import AICallLogRecord, AIReportRecord, SiteScoreRecord
from app.projects.service import data_quality, dataset, get_project
from app.scoring_engine.service import score_project


class ProjectNotFoundError(RuntimeError):
    pass


def latest_score(db: Session, project_id: str) -> dict[str, Any] | None:
    row = db.scalar(
        select(SiteScoreRecord)
        .where(SiteScoreRecord.project_id == project_id)
        .order_by(SiteScoreRecord.created_at.desc(), SiteScoreRecord.id.desc())
    )
    if not row:
        return None
    dimensions = row.dimension_scores or {}
    competitor_dimension = dimensions.get("competitor") or {}
    competitor_analysis = competitor_dimension.get("analysis") or {}
    support_dimension = dimensions.get("support") or {}
    supporting_analysis = support_dimension.get("analysis") or {}
    rent_dimension = dimensions.get("rent") or {}
    rent_analysis = rent_dimension.get("analysis") or {}
    return {
        "score_id": row.id,
        "project_id": row.project_id,
        "total_score": row.total_score,
        "level": row.level,
        "dimensions": dimensions,
        "competitor_analysis": competitor_analysis,
        "supporting_analysis": supporting_analysis,
        "rent_analysis": rent_analysis,
        "advantages": row.advantage_items,
        "risks": row.risk_items,
        "missing_data": row.missing_data,
        "confidence": row.confidence,
        "created_at": row.created_at,
    }


def build_ai_input(db: Session, project_id: str) -> AIAnalysisInput:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    project_dataset = dataset(db, project)
    score = latest_score(db, project_id)
    if score is None:
        score = score_project(db, project_id)
    quality = data_quality(db, project_id)
    pois = project_dataset.get("pois", [])
    confirmed_food_businesses = [
        row for row in project_dataset.get("food_businesses", []) if row.get("status") == "confirmed"
    ]
    confirmed_entertainments = [
        row for row in project_dataset.get("entertainments", []) if row.get("status") == "confirmed"
    ]
    environment = {
        "transport": [row for row in pois if row.get("category") == "transport"],
        "population": {
            "population_data": project_dataset.get("population_data") or {},
            "education_pois": [row for row in pois if row.get("category") == "education"],
            "residential_pois": [row for row in pois if row.get("category") == "residential"],
        },
        "support": {
            "food_pois": [row for row in pois if row.get("category") == "food"],
            "entertainment_pois": [row for row in pois if row.get("category") == "entertainment"],
            "food_businesses": confirmed_food_businesses,
            "entertainments": confirmed_entertainments,
        },
    }
    project_info = project_dataset["project"]
    return AIAnalysisInput(
        project={
            "project_id": project_info.get("project_id"),
            "name": project_info.get("name"),
            "business_type": project_info.get("business_type"),
        },
        location={
            "city": project_info.get("city"),
            "district": project_info.get("district"),
            "address": project_info.get("address"),
            "longitude": project_info.get("longitude"),
            "latitude": project_info.get("latitude"),
            "radius_meters": project_info.get("radius_meters"),
        },
        environment=environment,
        competitors=project_dataset.get("competitors", []),
        competitor_analysis=score.get("competitor_analysis") or {},
        supporting_analysis=score.get("supporting_analysis") or {},
        rent_analysis=score.get("rent_analysis") or {},
        # 不向 AI 发送未经评分过滤的原始租金记录，保留空字段仅用于结构兼容。
        rent={},
        score_result=score,
        data_quality=quality,
        risks=list(score.get("risks") or []) + list(quality.get("warnings") or []),
    )


def generate_ai_report(
    db: Session,
    project_id: str,
    *,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    deepseek = client or DeepSeekClient()
    try:
        deepseek.ensure_configured()
    except DeepSeekConfigError:
        return {"success": False, "message": "DeepSeek API Key未配置"}

    analysis_input = build_ai_input(db, project_id)
    input_dict = _json_safe(analysis_input.model_dump(mode="python"))
    started = time.perf_counter()
    report_id: int | None = None
    try:
        result = deepseek.generate_report(input_dict)
        report = AIReportRecord(
            project_id=project_id,
            input_snapshot=input_dict,
            score_snapshot=input_dict.get("score_result", {}),
            report_content=result.content,
            model_name=result.model,
            created_at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.flush()
        report_id = report.id
        _write_call_log(
            db,
            project_id=project_id,
            report_id=report_id,
            model_name=result.model,
            input_length=result.input_length,
            output_length=result.output_length,
            duration_ms=result.duration_ms,
            status="success",
        )
        db.commit()
        db.refresh(report)
        return {
            "success": True,
            "report_id": str(report.id),
            "content": report.report_content,
            "model": report.model_name,
            "created_at": report.created_at,
        }
    except Exception as exc:
        db.rollback()
        _write_call_log(
            db,
            project_id=project_id,
            report_id=report_id,
            model_name=deepseek.model,
            input_length=len(json.dumps(input_dict, ensure_ascii=False, default=str)),
            output_length=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
            status="failed",
            error_message=str(exc),
        )
        db.commit()
        raise


def _write_call_log(
    db: Session,
    *,
    project_id: str,
    report_id: int | None,
    model_name: str,
    input_length: int,
    output_length: int,
    duration_ms: int,
    status: str,
    error_message: str | None = None,
) -> None:
    db.add(
        AICallLogRecord(
            project_id=project_id,
            report_id=report_id,
            model_name=model_name,
            input_length=input_length,
            output_length=output_length,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
            created_at=datetime.now(timezone.utc),
        )
    )


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
