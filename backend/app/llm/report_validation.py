from __future__ import annotations

import re
from typing import Any


REQUIRED_REPORT_HEADINGS = (
    "## 一、项目概况",
    "## 二、核心结论",
    "## 三、交通环境",
    "## 四、竞争环境",
    "## 五、周边商业配套",
    "## 六、物业与租金",
    "## 七、数据缺失与风险",
    "## 八、最终建议",
)


class ReportTruthfulnessError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def _numeric_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()

    def add_number(number: int | float) -> None:
        normalized = f"{float(number):.12g}"
        tokens.add(normalized)
        if float(number).is_integer():
            tokens.add(str(int(number)))
        if 0 <= float(number) <= 1:
            percentage = float(number) * 100
            tokens.add(f"{percentage:.12g}")
            if percentage.is_integer():
                tokens.add(str(int(percentage)))

    def walk(item: Any) -> None:
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, (int, float)):
            add_number(item)
        elif isinstance(item, str):
            for match in re.findall(r"(?<![\w])\d+(?:\.\d+)?", item):
                tokens.add(f"{float(match):.12g}")
        elif isinstance(item, dict):
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return tokens


def _report_numbers(content: str) -> list[str]:
    body_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        stripped = re.sub(r"^\d+[.)、]\s*", "", stripped)
        body_lines.append(stripped)
    matches = re.findall(r"(?<![\w])\d+(?:\.\d+)?(?:%)?", "\n".join(body_lines))
    return [f"{float(item.rstrip('%')):.12g}" for item in matches]


def validate_report_content(content: str, snapshot: dict[str, Any]) -> None:
    errors: list[str] = []
    if not content.strip():
        errors.append("报告内容为空")
    if "# 电竞馆选址分析报告" not in content:
        errors.append("缺少固定报告标题")
    missing_headings = [heading for heading in REQUIRED_REPORT_HEADINGS if heading not in content]
    if missing_headings:
        errors.append(f"缺少固定章节：{'、'.join(missing_headings)}")
    elif [content.index(heading) for heading in REQUIRED_REPORT_HEADINGS] != sorted(
        content.index(heading) for heading in REQUIRED_REPORT_HEADINGS
    ):
        errors.append("固定章节顺序不正确")
    conclusion_match = re.search(r"## 二、核心结论\s*(.*?)(?=\n## 三、交通环境)", content, flags=re.DOTALL)
    conclusion = conclusion_match.group(1) if conclusion_match else ""
    if snapshot.get("allowed_conclusion") == "数据不足":
        if "数据不足" not in conclusion:
            errors.append("关键数据不足时核心结论必须为数据不足")
    elif not any(value in conclusion for value in ("推荐", "谨慎", "不推荐")):
        errors.append("核心结论必须为推荐、谨慎或不推荐")
    forbidden_phrases = [phrase for phrase in ("预计", "可能约", "一般情况下", "据经验") if phrase in content]
    if forbidden_phrases:
        errors.append(f"包含禁止的推测表达：{'、'.join(forbidden_phrases)}")
    allowed_numbers = _numeric_tokens(snapshot)
    unsupported = sorted({number for number in _report_numbers(content) if number not in allowed_numbers}, key=float)
    if unsupported:
        errors.append(f"报告包含快照中不存在的数字：{', '.join(unsupported)}")
    if errors:
        raise ReportTruthfulnessError(errors)
