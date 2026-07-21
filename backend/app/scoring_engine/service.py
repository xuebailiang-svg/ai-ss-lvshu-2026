from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import RentDataRecord, SiteScoreRecord
from app.projects.service import dataset, get_project, row_to_dict, rows_for_project
from app.scoring_engine.calculator import ProjectScoreCalculator
from app.scoring_engine.config_service import rules_with_db_weights
from app.scoring_engine.rules import load_rules


class ProjectNotFoundError(RuntimeError):
    pass


def score_project(db: Session, project_id: str, *, rules_path: str | Path | None = None) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    rules = load_rules(rules_path)
    if rules_path is None:
        rules = rules_with_db_weights(db, rules)
    project_dataset = dataset(db, project)
    # 评分使用完整租金样本集；项目 dataset 的 rent_data 仍保留为兼容旧调用的最新记录。
    project_dataset["rent_records"] = rows_for_project(db, RentDataRecord, project.project_id)
    result = ProjectScoreCalculator(rules).calculate(project_dataset)
    record = SiteScoreRecord(
        project_id=project.project_id,
        total_score=result["total_score"],
        level=result["level"],
        dimension_scores=result["dimensions"],
        advantage_items=result["advantages"],
        risk_items=result["risks"],
        missing_data=result["missing_data"],
        confidence=result["confidence"],
        created_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "project_id": project.project_id,
        **result,
        "score_id": record.id,
        "created_at": record.created_at,
        "scoring_config": rules.get("scoring_config", {}),
    }


def score_record_to_dict(record: SiteScoreRecord) -> dict[str, Any]:
    return row_to_dict(record)
