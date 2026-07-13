from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import SiteScoreRecord
from app.projects.service import dataset, get_project, row_to_dict
from app.scoring_engine.calculator import ProjectScoreCalculator
from app.scoring_engine.rules import load_rules


class ProjectNotFoundError(RuntimeError):
    pass


def score_project(db: Session, project_id: str, *, rules_path: str | Path | None = None) -> dict[str, Any]:
    project = get_project(db, project_id)
    if not project:
        raise ProjectNotFoundError("Project not found")
    rules = load_rules(rules_path)
    project_dataset = dataset(db, project)
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
    }


def score_record_to_dict(record: SiteScoreRecord) -> dict[str, Any]:
    return row_to_dict(record)
