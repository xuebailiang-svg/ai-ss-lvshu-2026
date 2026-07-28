from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

from app.data_model import RegionalStatisticData


METRIC_SPECS: tuple[dict[str, Any], ...] = (
    {
        "code": "resident_population",
        "name": "常住人口",
        "unit": "万人",
        "patterns": (
            r"(?:年末)?(?:全省|全市|全区)?常住人口(?:为|达到|共)?\s*([\d,.]+)\s*万人",
            r"(?:年末)?(?:全省|全市|全区)?常住人口(?:为|达到|共)?\s*([\d,.]+)\s*人",
            r"(?:年末)?全国人口(?:为|达到|共)?\s*([\d,.]+)\s*万人",
        ),
    },
    {
        "code": "registered_population",
        "name": "户籍人口",
        "unit": "万人",
        "patterns": (
            r"(?:年末)?(?:全省|全市|全区)?户籍人口(?:为|达到|共)?\s*([\d,.]+)\s*万人",
            r"(?:年末)?(?:全省|全市|全区)?户籍人口(?:为|达到|共)?\s*([\d,.]+)\s*人",
        ),
    },
    {
        "code": "urbanization_rate",
        "name": "城镇化率",
        "unit": "%",
        "patterns": (r"城镇化率(?:为|达到)?\s*([\d.]+)\s*%",),
    },
    {
        "code": "gdp",
        "name": "地区生产总值",
        "unit": "亿元",
        "patterns": (
            r"地区生产总值(?:（GDP）)?(?:为|达到|完成)?\s*([\d,.]+)\s*亿元",
            r"生产总值(?:（GDP）)?(?:为|达到|完成)?\s*([\d,.]+)\s*亿元",
            r"国内生产总值(?:（GDP）)?(?:为|达到|完成)?\s*([\d,.]+)\s*亿元",
        ),
    },
    {
        "code": "tertiary_industry_share",
        "name": "第三产业占比",
        "unit": "%",
        "patterns": (
            r"第三产业(?:增加值)?(?:占(?:地区|国内)?生产总值(?:的)?比重|占比)(?:为|达到)?\s*([\d.]+)\s*%",
        ),
    },
    {
        "code": "retail_sales_total",
        "name": "社会消费品零售总额",
        "unit": "亿元",
        "patterns": (
            r"社会消费品零售总额(?:为|达到|完成)?\s*([\d,.]+)\s*亿元",
        ),
    },
    {
        "code": "disposable_income_per_capita",
        "name": "居民人均可支配收入",
        "unit": "元",
        "patterns": (
            r"(?:全体)?居民人均可支配收入(?:为|达到)?\s*([\d,.]+)\s*元",
        ),
    },
    {
        "code": "consumption_expenditure_per_capita",
        "name": "居民人均消费支出",
        "unit": "元",
        "patterns": (
            r"(?:全体)?居民人均消费支出(?:为|达到)?\s*([\d,.]+)\s*元",
        ),
    },
    {
        "code": "employment_total",
        "name": "从业人员",
        "unit": "万人",
        "patterns": (
            r"(?:全省|全市|全区)?(?:就业人员|从业人员)(?:为|达到|共)?\s*([\d,.]+)\s*万人",
        ),
    },
)


def html_to_text(content: str) -> str:
    content = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", content)
    content = re.sub(r"(?s)<[^>]+>", " ", content)
    content = html.unescape(content)
    return re.sub(r"\s+", " ", content).strip()


def detect_period(text: str, default: str = "") -> str:
    match = re.search(r"(20\d{2})年", text[:3000])
    return match.group(1) if match else default


def _number(raw: str, *, unit: str, matched_text: str) -> float:
    value = float(raw.replace(",", ""))
    if unit == "万人" and "万人" not in matched_text and matched_text.endswith("人"):
        return round(value / 10000, 4)
    return value


def parse_official_text(
    text: str,
    *,
    scope_level: str,
    scope_code: str,
    scope_name: str,
    source_name: str,
    source_url: str,
    source_format: str,
    stat_period: str = "",
    published_at: datetime | None = None,
) -> list[RegionalStatisticData]:
    normalized = re.sub(r"\s+", "", text)
    period = stat_period or detect_period(text)
    if not period:
        return []
    confidence = {"api": .95, "xlsx": .95, "html": .85, "pdf": .75, "manual": .8}.get(source_format, .8)
    status = "pending_review" if source_format == "pdf" else "confirmed"
    items: list[RegionalStatisticData] = []
    for spec in METRIC_SPECS:
        match = None
        for pattern in spec["patterns"]:
            match = re.search(pattern, normalized)
            if match:
                break
        if not match:
            continue
        value = _number(match.group(1), unit=spec["unit"], matched_text=match.group(0))
        items.append(
            RegionalStatisticData(
                metric_code=spec["code"],
                metric_name=spec["name"],
                value_numeric=value,
                unit=spec["unit"],
                scope_level=scope_level,
                scope_code=scope_code,
                scope_name=scope_name,
                stat_period=period,
                source_name=source_name,
                source_url=source_url,
                source_format=source_format,
                published_at=published_at,
                source="government_stats",
                status=status,
                confidence=confidence,
                timestamp=datetime.now(timezone.utc),
                raw_data={
                    "matched_text": match.group(0),
                    "official_scope": scope_name,
                    "stat_period": period,
                },
            )
        )
    age_patterns = {
        "age_0_14": r"0[—\-~至]14岁人口(?:为|共)?([\d,.]+)(万人|人)|0[—\-~至]14岁人口占(?:全国|全省|全市|全区)?人口的比重为([\d.]+)%",
        "age_15_64": r"15[—\-~至]64岁人口(?:为|共)?([\d,.]+)(万人|人)|15[—\-~至]64岁人口占(?:全国|全省|全市|全区)?人口的比重为([\d.]+)%",
        "age_65_plus": r"65岁及以上人口(?:为|共)?([\d,.]+)(万人|人)|65岁及以上人口占(?:全国|全省|全市|全区)?人口的比重为([\d.]+)%",
    }
    age_values: dict[str, dict[str, Any]] = {}
    age_matches: list[str] = []
    for key, pattern in age_patterns.items():
        match = re.search(pattern, normalized)
        if not match:
            continue
        if match.group(3):
            age_values[key] = {"value": float(match.group(3)), "unit": "%"}
        else:
            raw_value = float(match.group(1).replace(",", ""))
            unit = match.group(2)
            age_values[key] = {
                "value": round(raw_value / 10000, 4) if unit == "人" else raw_value,
                "unit": "万人",
            }
        age_matches.append(match.group(0))
    if age_values:
        display_names = {
            "age_0_14": "0-14岁",
            "age_15_64": "15-64岁",
            "age_65_plus": "65岁及以上",
        }
        value_text = "；".join(
            f"{display_names[key]}{value['value']}{value['unit']}"
            for key, value in age_values.items()
        )
        items.append(
            RegionalStatisticData(
                metric_code="population_age_structure",
                metric_name="人口年龄结构",
                value_text=value_text,
                scope_level=scope_level,
                scope_code=scope_code,
                scope_name=scope_name,
                stat_period=period,
                source_name=source_name,
                source_url=source_url,
                source_format=source_format,
                published_at=published_at,
                source="government_stats",
                status=status,
                confidence=confidence,
                timestamp=datetime.now(timezone.utc),
                raw_data={
                    "age_groups": age_values,
                    "matched_text": age_matches,
                    "official_scope": scope_name,
                    "stat_period": period,
                },
            )
        )
    return items


def parse_structured_rows(
    rows: list[dict[str, Any]],
    *,
    source_name: str,
    source_url: str,
    source_format: str = "api",
) -> tuple[list[RegionalStatisticData], list[dict[str, Any]]]:
    """解析官方 JSON/结构化接口的标准行，不对缺失值做任何推断。"""
    items: list[RegionalStatisticData] = []
    errors: list[dict[str, Any]] = []
    required = {
        "metric_code",
        "metric_name",
        "scope_level",
        "scope_code",
        "scope_name",
        "stat_period",
    }
    for index, row in enumerate(rows, start=1):
        missing = [key for key in required if not str(row.get(key) or "").strip()]
        if missing:
            errors.append({"row": index, "reason": f"缺少字段：{', '.join(sorted(missing))}"})
            continue
        raw_numeric = row.get("value_numeric")
        try:
            value_numeric = (
                None
                if raw_numeric in (None, "")
                else float(str(raw_numeric).replace(",", ""))
            )
        except (TypeError, ValueError):
            errors.append({"row": index, "reason": "value_numeric不是数字"})
            continue
        items.append(
            RegionalStatisticData(
                metric_code=str(row["metric_code"]).strip(),
                metric_name=str(row["metric_name"]).strip(),
                value_numeric=value_numeric,
                value_text=str(row.get("value_text") or "").strip() or None,
                unit=str(row.get("unit") or "").strip() or None,
                scope_level=str(row["scope_level"]).strip(),
                scope_code=str(row["scope_code"]).strip(),
                scope_name=str(row["scope_name"]).strip(),
                stat_period=str(row["stat_period"]).strip(),
                source_name=source_name,
                source_url=source_url,
                source_format=source_format,
                source="government_stats",
                status="confirmed",
                confidence=.95,
                timestamp=datetime.now(timezone.utc),
                raw_data={"structured": True, "source_row": row},
            )
        )
    return items, errors
