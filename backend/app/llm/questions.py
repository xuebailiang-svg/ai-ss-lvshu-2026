from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import DeepSeekClient, DeepSeekConfigError
from app.llm.prompts import AI_QUESTION_SELECTION_PROMPT
from app.manual_input.audit import apply_manual_changes, manual_meta
from app.models import SupplementRecord, UnifiedCompetitorRecord
from app.projects.service import get_project, row_to_dict


MAX_ROUNDS = 2
MAX_QUESTIONS_PER_ROUND = 3
MAX_QUESTIONS_TOTAL = 5


class QuestionProjectNotFoundError(RuntimeError):
    pass


class QuestionValidationError(ValueError):
    pass


class SelectedQuestion(BaseModel):
    candidate_id: str


class SelectedQuestions(BaseModel):
    questions: list[SelectedQuestion] = Field(default_factory=list, max_length=MAX_QUESTIONS_PER_ROUND)


def _question_rows(db: Session, project_id: str) -> list[SupplementRecord]:
    return list(
        db.scalars(
            select(SupplementRecord).where(
                SupplementRecord.project_id == project_id,
                SupplementRecord.target_type == "ai_question",
            ).order_by(SupplementRecord.id.asc())
        ).all()
    )


def _candidate(
    candidate_id: str,
    field_key: str,
    target_type: str,
    target_id: str,
    title: str,
    help_text: str,
    answer_type: str,
    *,
    unit: str | None = None,
    options: list[dict[str, str]] | None = None,
    priority: int,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "field_key": field_key,
        "target_type": target_type,
        "target_id": target_id,
        "title": title,
        "help_text": help_text,
        "answer_type": answer_type,
        "unit": unit,
        "options": options or [],
        "priority": priority,
    }


def allowed_question_candidates(db: Session, project_id: str) -> list[dict[str, Any]]:
    project = get_project(db, project_id)
    if not project:
        raise QuestionProjectNotFoundError("Project not found")
    asked = {str(row.field_name) for row in _question_rows(db, project_id)}
    candidates: list[dict[str, Any]] = []
    competitors = list(
        db.scalars(
            select(UnifiedCompetitorRecord).where(
                UnifiedCompetitorRecord.project_id == project_id,
                UnifiedCompetitorRecord.status != "rejected",
            ).order_by(UnifiedCompetitorRecord.distance_meters.asc().nullslast(), UnifiedCompetitorRecord.id.asc())
        ).all()
    )[:3]
    for index, row in enumerate(competitors):
        unknown = set(manual_meta(row.raw_data).get("unknown_fields") or [])
        base = f"competitor:{row.id}"
        fields = [
            ("hour_price", row.hour_price, "number", "元/小时", "这家竞品的普通小时价是多少？", "填写现场价目表或可靠人工询价结果。", 10),
            ("machine_count", row.machine_count, "integer", "台", "这家竞品大约有多少台机器？", "可填写现场清点或店员确认的数量。", 20),
            ("gpu", row.gpu, "text", None, "这家竞品的主流显卡配置是什么？", "例如 RTX 4060；不知道可以直接选择不知道。", 30),
            ("occupancy_rate", row.occupancy_rate, "percentage", "%", "现场观察时，这家竞品的上座率大约是多少？", "填写 0–100，并以实际观察为准。", 40),
        ]
        for field, value, answer_type, unit, title, help_text, priority in fields:
            field_key = f"{base}:{field}"
            if value not in (None, "") or field in unknown or field_key in asked:
                continue
            candidates.append(
                _candidate(
                    field_key, field_key, "competitor", str(row.id), f"{row.name}：{title}", help_text,
                    answer_type, unit=unit, priority=priority + index,
                )
            )

    property_row = db.scalar(
        select(SupplementRecord).where(
            SupplementRecord.project_id == project_id,
            SupplementRecord.target_type == "candidate_property",
            SupplementRecord.field_name == "manual_detail",
        ).order_by(SupplementRecord.id.desc())
    )
    values = dict(property_row.value) if property_row and isinstance(property_row.value, dict) else {}
    unknown = set(manual_meta(property_row.raw_data).get("unknown_fields") or []) if property_row else set()
    property_fields = [
        ("address", "text", None, "候选物业的详细地址是什么？", "填写实际考察物业地址，不是项目商圈名称。", 1),
        ("area_sqm", "number", "平方米", "候选物业的可用面积是多少？", "填写可实际经营使用的面积。", 2),
        ("monthly_rent", "money", "元/月", "候选物业的月租金是多少？", "填写房东或合同口径的月租金。", 3),
        ("use_allowed", "boolean", None, "物业是否允许经营电竞馆？", "以房东、物业或主管部门的明确答复为准。", 4),
        ("power_capacity_kw", "number", "kW", "物业现有供电容量是多少？", "不知道可以选择不知道，不要估算。", 5),
        ("fire_confirmed", "boolean", None, "物业消防条件是否已现场确认？", "只填写实际核实结果。", 6),
    ]
    for field, answer_type, unit, title, help_text, priority in property_fields:
        field_key = f"property:primary:{field}"
        if values.get(field) not in (None, "") or field in unknown or field_key in asked:
            continue
        candidates.append(
            _candidate(
                field_key, field_key, "property", "primary", title, help_text, answer_type,
                unit=unit,
                options=[{"label": "是", "value": "true"}, {"label": "否", "value": "false"}]
                if answer_type == "boolean" else [],
                priority=priority,
            )
        )
    return sorted(candidates, key=lambda item: (item["priority"], item["candidate_id"]))


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("AI question output must be an object")
    return value


def _select_with_ai(candidates: list[dict[str, Any]], client: DeepSeekClient) -> list[dict[str, Any]]:
    result = client.generate_report(
        {"allowed_candidates": [{key: item[key] for key in ("candidate_id", "title", "help_text", "answer_type", "unit", "priority")} for item in candidates]},
        prompt=AI_QUESTION_SELECTION_PROMPT,
    )
    selected = SelectedQuestions.model_validate(_extract_json(result.content))
    allowed = {item["candidate_id"]: item for item in candidates}
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in selected.questions:
        if item.candidate_id not in allowed or item.candidate_id in seen:
            raise QuestionValidationError("AI returned an invalid or duplicate candidate_id")
        base = dict(allowed[item.candidate_id])
        output.append(base)
        seen.add(item.candidate_id)
    return output


def generate_questions(
    db: Session,
    project_id: str,
    *,
    continue_round: bool = False,
    client: DeepSeekClient | None = None,
) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise QuestionProjectNotFoundError("Project not found")
    rows = _question_rows(db, project_id)
    existing_pending = [row for row in rows if row.status == "pending_review"]
    if existing_pending:
        round_number = max(int((row.value or {}).get("round") or 1) for row in existing_pending)
        return _response(existing_pending, round_number, len(rows), len(allowed_question_candidates(db, project_id)), "请先回答当前问题")
    asked_count = len(rows)
    current_round = max((int((row.value or {}).get("round") or 1) for row in rows), default=0)
    if asked_count >= MAX_QUESTIONS_TOTAL or current_round >= MAX_ROUNDS:
        return _response([], current_round, asked_count, 0, "已达到提问上限，可以继续生成报告", status="limit_reached")
    if current_round >= 1 and not continue_round:
        remaining = len(allowed_question_candidates(db, project_id))
        return _response([], current_round, asked_count, remaining, "第一轮已完成；如确有需要可继续第二轮", status="round_complete")
    candidates = allowed_question_candidates(db, project_id)
    if not candidates:
        return _response([], current_round, asked_count, 0, "没有需要继续追问的重要信息", status="complete")
    limit = min(MAX_QUESTIONS_PER_ROUND, MAX_QUESTIONS_TOTAL - asked_count)
    deepseek = client or DeepSeekClient()
    try:
        deepseek.ensure_configured()
        selected = _select_with_ai(candidates, deepseek)[:limit]
    except (
        DeepSeekConfigError,
        httpx.HTTPError,
        json.JSONDecodeError,
        ValidationError,
        QuestionValidationError,
        ValueError,
        TimeoutError,
    ):
        return _response([], current_round, asked_count, len(candidates), "AI 未返回有效的结构化问题，已安全跳过，不阻塞报告", status="skipped")
    if not selected:
        return _response([], current_round, asked_count, len(candidates), "AI 判断无需继续追问", status="complete")
    round_number = current_round + 1
    now = datetime.now(timezone.utc)
    saved: list[SupplementRecord] = []
    for item in selected:
        question_id = f"q_{uuid4().hex[:16]}"
        value = {**item, "question_id": question_id, "round": round_number, "answer_status": "pending"}
        row = SupplementRecord(
            project_id=project_id,
            target_type="ai_question",
            target_id=question_id,
            field_name=item["field_key"],
            value=value,
            source="ai_selected",
            confidence=1.0,
            status="pending_review",
            raw_data={},
            timestamp=now,
            created_time=now,
        )
        db.add(row)
        saved.append(row)
    db.commit()
    for row in saved:
        db.refresh(row)
    return _response(saved, round_number, asked_count + len(saved), max(0, len(candidates) - len(saved)), "请回答以下重要问题")


def _question_public(row: SupplementRecord) -> dict[str, Any]:
    value = dict(row.value) if isinstance(row.value, dict) else {}
    return {
        key: value.get(key)
        for key in (
            "question_id", "field_key", "target_type", "target_id", "title", "help_text",
            "answer_type", "unit", "options", "round",
        )
    }


def _response(
    rows: list[SupplementRecord],
    round_number: int,
    asked_count: int,
    remaining: int,
    message: str,
    *,
    status: str = "questions_ready",
) -> dict[str, Any]:
    return {
        "success": True,
        "status": status,
        "round": round_number,
        "questions": [_question_public(row) for row in rows],
        "asked_count": asked_count,
        "remaining_candidate_count": remaining,
        "message": message,
    }


def _coerce_value(answer_type: str, value: Any) -> Any:
    if answer_type in {"number", "money", "percentage"}:
        number = float(value)
        if number < 0 or (answer_type == "percentage" and number > 100):
            raise QuestionValidationError("numeric answer out of range")
        return number / 100 if answer_type == "percentage" else number
    if answer_type == "integer":
        number = int(value)
        if number < 0:
            raise QuestionValidationError("integer answer out of range")
        return number
    if answer_type == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "1", "yes"}:
            return True
        if str(value).lower() in {"false", "0", "no"}:
            return False
        raise QuestionValidationError("invalid boolean answer")
    text = str(value or "").strip()
    if not text:
        raise QuestionValidationError("answer cannot be empty")
    return text


def _save_competitor_answer(db: Session, project_id: str, row: SupplementRecord, value: Any, unknown: bool) -> None:
    question = dict(row.value or {})
    competitor = db.scalar(
        select(UnifiedCompetitorRecord).where(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.id == int(question["target_id"]),
        )
    )
    if not competitor or competitor.status == "rejected":
        raise QuestionValidationError("question target is no longer available")
    field = str(question["field_key"]).rsplit(":", 1)[-1]
    meta = manual_meta(competitor.raw_data)
    unknown_fields = set(meta.get("unknown_fields") or [])
    old_value = getattr(competitor, field, None)
    changes: dict[str, Any] = {}
    if old_value not in (None, ""):
        raise QuestionValidationError("field already has a value")
    if unknown:
        unknown_fields.add(field)
    else:
        setattr(competitor, field, value)
        changes[field] = value
        unknown_fields.discard(field)
    competitor.raw_data = apply_manual_changes(
        db, project_id=project_id, target_type="competitor", target_id=competitor.id,
        raw_data=competitor.raw_data, old_values={field: old_value}, changes=changes,
        unknown_fields=sorted(unknown_fields),
    )


def _save_property_answer(db: Session, project_id: str, row: SupplementRecord, value: Any, unknown: bool) -> None:
    question = dict(row.value or {})
    property_row = db.scalar(
        select(SupplementRecord).where(
            SupplementRecord.project_id == project_id,
            SupplementRecord.target_type == "candidate_property",
            SupplementRecord.field_name == "manual_detail",
        ).order_by(SupplementRecord.id.desc())
    )
    now = datetime.now(timezone.utc)
    if not property_row:
        property_row = SupplementRecord(
            project_id=project_id, target_type="candidate_property", target_id="primary",
            field_name="manual_detail", value={}, source="manual", confidence=0.8,
            status="confirmed", raw_data={}, timestamp=now, created_time=now,
        )
        db.add(property_row)
        db.flush()
    values = dict(property_row.value) if isinstance(property_row.value, dict) else {}
    field = str(question["field_key"]).rsplit(":", 1)[-1]
    old_value = values.get(field)
    meta = manual_meta(property_row.raw_data)
    unknown_fields = set(meta.get("unknown_fields") or [])
    changes: dict[str, Any] = {}
    if old_value not in (None, ""):
        raise QuestionValidationError("field already has a value")
    if unknown:
        unknown_fields.add(field)
    else:
        values[field] = value
        changes[field] = value
        unknown_fields.discard(field)
    property_row.value = values
    property_row.timestamp = now
    property_row.raw_data = apply_manual_changes(
        db, project_id=project_id, target_type="candidate_property", target_id="primary",
        raw_data=property_row.raw_data, old_values={field: old_value}, changes=changes,
        unknown_fields=sorted(unknown_fields),
    )


def save_answers(db: Session, project_id: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
    if not get_project(db, project_id):
        raise QuestionProjectNotFoundError("Project not found")
    rows = {str(row.target_id): row for row in _question_rows(db, project_id)}
    saved = unknown_count = skipped = 0
    now = datetime.now(timezone.utc)
    for answer in answers:
        row = rows.get(str(answer.get("question_id")))
        if not row or row.status != "pending_review":
            raise QuestionValidationError("question does not exist or has already been answered")
        question = dict(row.value or {})
        unknown = bool(answer.get("unknown"))
        skip = bool(answer.get("skip"))
        if unknown and skip:
            raise QuestionValidationError("answer cannot be both unknown and skipped")
        if not unknown and not skip:
            value = _coerce_value(str(question.get("answer_type")), answer.get("value"))
            if question.get("target_type") == "competitor":
                _save_competitor_answer(db, project_id, row, value, False)
            elif question.get("target_type") == "property":
                _save_property_answer(db, project_id, row, value, False)
            else:
                raise QuestionValidationError("unsupported question target")
            saved += 1
            answer_status = "answered"
        elif unknown:
            if question.get("target_type") == "competitor":
                _save_competitor_answer(db, project_id, row, None, True)
            elif question.get("target_type") == "property":
                _save_property_answer(db, project_id, row, None, True)
            unknown_count += 1
            answer_status = "unknown"
            value = None
        else:
            skipped += 1
            answer_status = "skipped"
            value = None
        row.value = {**question, "answer_status": answer_status, "answer": value, "answered_at": now.isoformat()}
        row.status = "confirmed" if answer_status in {"answered", "unknown"} else "rejected"
        row.source = "user_provided" if answer_status in {"answered", "unknown"} else "user_skipped"
        row.timestamp = now
    db.commit()
    all_rows = _question_rows(db, project_id)
    can_continue = len(all_rows) < MAX_QUESTIONS_TOTAL and max(
        (int((row.value or {}).get("round") or 1) for row in all_rows), default=0
    ) < MAX_ROUNDS and bool(allowed_question_candidates(db, project_id))
    return {
        "success": True,
        "saved_count": saved,
        "unknown_count": unknown_count,
        "skipped_count": skipped,
        "can_continue": can_continue,
        "message": "回答已保存到当前项目",
    }
