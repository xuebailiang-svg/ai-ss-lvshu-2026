from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import DeepSeekClient, DeepSeekConfigError
from app.llm.prompts import AI_DATA_REVIEW_PROMPT, FINAL_PROJECT_REPORT_PROMPT
from app.llm.report_validation import ReportTruthfulnessError, validate_report_content
from app.llm.schemas import AIAnalysisInput
from app.llm.snapshot import SnapshotProjectNotFoundError, build_final_project_snapshot
from app.models import AICallLogRecord, AIReportRecord, SiteScoreRecord
from app.demo_data.service import simulation_data_summary
from app.memory.service import relevant_memory_context
from app.projects.service import data_quality, dataset, get_project
from app.scoring_engine.service import score_project
from app.data_source.government_stats.service import city_insight as build_city_insight
from app.data_source.crawler.review_service import confirmed_evidence_summary


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
    simulation_summary = simulation_data_summary(db, project_id)
    city_context = build_city_insight(db, project)
    memories = relevant_memory_context(
        db,
        project_id,
        tags=[project.city, project.business_type, "电竞馆", "竞品", "租金", "夜经济"],
    )
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
        city_insight=city_context,
        # 不向 AI 发送未经评分过滤的原始租金记录，保留空字段仅用于结构兼容。
        rent={},
        score_result=score,
        data_quality=quality,
        simulation_data_summary=simulation_summary,
        memory_context=memories,
        crawler_evidence_summary=confirmed_evidence_summary(db, project_id),
        risks=list(score.get("risks") or []) + list(quality.get("warnings") or []),
    )


def build_ai_review_input(db: Session, project_id: str) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")

    project_dataset = dataset(db, project)
    quality = data_quality(db, project_id)
    simulation_summary = simulation_data_summary(db, project_id)
    score = latest_score(db, project_id)
    pois = project_dataset.get("pois", [])
    competitors = project_dataset.get("competitors", [])
    food_businesses = project_dataset.get("food_businesses", [])
    entertainments = project_dataset.get("entertainments", [])
    rent_records = project_dataset.get("rent_data")

    confirmed_competitors = [row for row in competitors if row.get("status") == "confirmed"]
    pending_competitors = [row for row in competitors if row.get("status") == "pending_review"]
    confirmed_food = [row for row in food_businesses if row.get("status") == "confirmed"]
    confirmed_entertainments = [row for row in entertainments if row.get("status") == "confirmed"]

    return _json_safe(
        {
            "project": project_dataset.get("project", {}),
            "data_inventory": {
                "poi_count": len(pois),
                "transport_poi_count": len([row for row in pois if row.get("category") == "transport"]),
                "education_poi_count": len([row for row in pois if row.get("category") == "education"]),
                "residential_poi_count": len([row for row in pois if row.get("category") == "residential"]),
                "competitor_count": len(competitors),
                "confirmed_competitor_count": len(confirmed_competitors),
                "pending_competitor_count": len(pending_competitors),
                "food_business_count": len(food_businesses),
                "confirmed_food_business_count": len(confirmed_food),
                "entertainment_count": len(entertainments),
                "confirmed_entertainment_count": len(confirmed_entertainments),
                "rent_record_count": 1 if rent_records else 0,
            },
            "data_quality": quality,
            "city_insight": build_city_insight(db, project),
            "simulation_data_summary": simulation_summary,
            "latest_score": score or {},
            "existing_data": {
                "sample_competitors": [
                    {
                        "name": row.get("name"),
                        "status": row.get("status"),
                        "distance_meters": row.get("distance_meters"),
                        "source": row.get("source"),
                    }
                    for row in competitors[:10]
                ],
                "sample_food_businesses": [
                    {
                        "name": row.get("name"),
                        "status": row.get("status"),
                        "source": row.get("source"),
                    }
                    for row in food_businesses[:10]
                ],
                "sample_entertainments": [
                    {
                        "name": row.get("name"),
                        "status": row.get("status"),
                        "source": row.get("source"),
                    }
                    for row in entertainments[:10]
                ],
            },
            "review_goal": "判断当前数据是否足够支持电竞馆选址报告，并输出人工补充清单。",
        }
    )


def generate_ai_data_review(
    db: Session,
    project_id: str,
    *,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")

    quality = data_quality(db, project_id)
    deepseek = client or DeepSeekClient()
    try:
        deepseek.ensure_configured()
    except DeepSeekConfigError:
        return {"success": False, "message": "DeepSeek API Key未配置", "data_quality": quality}

    review_input = build_ai_review_input(db, project_id)
    result = deepseek.generate_report(review_input, prompt=AI_DATA_REVIEW_PROMPT)
    return {
        "success": True,
        "content": result.content,
        "model": result.model,
        "reviewed_at": datetime.now(timezone.utc),
        "data_quality": quality,
    }


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

    try:
        snapshot = build_final_project_snapshot(db, project_id)
    except SnapshotProjectNotFoundError:
        raise ProjectNotFoundError("Project not found") from None
    readiness = snapshot.get("data_readiness") or {}
    input_dict = {"final_project_snapshot": _json_safe(snapshot)}
    if readiness.get("status") == "blocked":
        content = _data_insufficient_report(snapshot)
        report = AIReportRecord(
            project_id=project_id,
            input_snapshot=input_dict,
            score_snapshot={},
            report_content=content,
            model_name="system-readiness",
            created_at=datetime.now(timezone.utc),
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        return {
            "success": True,
            "report_id": str(report.id),
            "content": report.report_content,
            "model": report.model_name,
            "created_at": report.created_at,
            "message": "技术前置条件不足，已生成数据不足报告",
            "snapshot_version": snapshot.get("snapshot_version"),
            "validation_status": "system_generated",
        }

    started = time.perf_counter()
    report_id: int | None = None
    try:
        result = deepseek.generate_report(input_dict, prompt=FINAL_PROJECT_REPORT_PROMPT)
        try:
            validate_report_content(result.content, snapshot)
        except ReportTruthfulnessError as first_error:
            _write_call_log(
                db,
                project_id=project_id,
                report_id=None,
                model_name=result.model,
                input_length=result.input_length,
                output_length=result.output_length,
                duration_ms=result.duration_ms,
                status="validation_failed",
                error_message=str(first_error),
            )
            db.commit()
            retry_input = {
                **input_dict,
                "validation_feedback": {
                    "message": "上一版报告未通过真实性校验，请重新生成并严格遵守固定章节和数字白名单。",
                    "errors": first_error.errors,
                },
            }
            result = deepseek.generate_report(retry_input, prompt=FINAL_PROJECT_REPORT_PROMPT)
            try:
                validate_report_content(result.content, snapshot)
            except ReportTruthfulnessError as final_error:
                _write_call_log(
                    db,
                    project_id=project_id,
                    report_id=None,
                    model_name=result.model,
                    input_length=result.input_length,
                    output_length=result.output_length,
                    duration_ms=result.duration_ms,
                    status="validation_failed",
                    error_message=str(final_error),
                )
                db.commit()
                return {
                    "success": False,
                    "message": "AI 报告两次未通过真实性校验，未发布。请补充数据后重试。",
                    "snapshot_version": snapshot.get("snapshot_version"),
                    "validation_status": "failed",
                }
        report = AIReportRecord(
            project_id=project_id,
            input_snapshot=input_dict,
            score_snapshot={},
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
            "snapshot_version": snapshot.get("snapshot_version"),
            "validation_status": "passed",
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


def _data_insufficient_report(snapshot: dict[str, Any]) -> str:
    project = snapshot.get("project") or {}
    location = project.get("location") or {}
    address = ((location.get("address") or {}).get("value") if isinstance(location.get("address"), dict) else None) or "地址待确认"
    radius = ((location.get("radius_meters") or {}).get("value") if isinstance(location.get("radius_meters"), dict) else None)
    scope = f"{radius} 米" if radius is not None else "范围待确认"
    groups = (snapshot.get("data_readiness") or {}).get("groups") or {}
    items = [item for values in groups.values() for item in values if item.get("status") in {"blocked", "missing", "acknowledged_unknown"}]
    missing_lines = "\n".join(f"- {item.get('label')}：{item.get('summary')}" for item in items) or "- 当前没有更多可核实信息。"
    return (
        "# 电竞馆选址分析报告\n\n"
        "## 一、项目概况\n\n"
        f"- 项目地址：{address}\n- 分析范围：{scope}\n- 数据来源：用户输入与高德采集事实。\n\n"
        "## 二、核心结论\n\n"
        "**数据不足。** 当前技术前置条件尚未完成，系统未调用大模型，也未根据缺失数据进行推测。\n\n"
        "## 三、交通环境\n\n当前缺少可用于报告的完整高德交通查询结果，无法判断。\n\n"
        "## 四、竞争环境\n\n当前项目数据不足以确认竞争环境，无法判断。\n\n"
        "## 五、周边商业配套\n\n当前项目数据不足以确认周边商业配套，无法判断。\n\n"
        "## 六、物业与租金\n\n只接受用户实际填写的物业与租金事实；当前缺失项不会被推测。\n\n"
        f"## 七、数据缺失与风险\n\n{missing_lines}\n\n"
        "## 八、最终建议\n\n"
        "### 基于已有事实可以确定\n\n- 当前只能确定项目基础信息，不能形成投资推荐。\n\n"
        "### 签约前仍需现场核实\n\n- 先完成地址定位和高德 POI 采集，再补充候选物业与核心竞品事实。\n"
    )


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
