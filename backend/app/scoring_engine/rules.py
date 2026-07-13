from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_RULE_PATH = Path(__file__).with_name("default.yaml")


def load_rules(path: str | Path | None = None) -> dict[str, Any]:
    rule_path = Path(path) if path else DEFAULT_RULE_PATH
    data = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
    return data
