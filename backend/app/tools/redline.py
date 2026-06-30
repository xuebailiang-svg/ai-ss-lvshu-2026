from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class RedlineCheckTool(BaseTool):
    tool_name = "redline_check"
    sensitive_categories = {"小学", "中学", "幼儿园", "敏感场所"}
    sensitive_keywords = ["幼儿园", "小学", "中学", "学校", "政府机构", "政府机关"]
    radius_meters = 200

    async def run(self, context: dict) -> ToolResult:
        geo = (context.get("agent_state") or {}).get("geo") or context.get("geocode") or {}
        pois = (context.get("agent_state") or {}).get("poi") or context.get("pois") or []
        sensitive = [
            row for row in pois
            if self._is_sensitive(row)
            and row.get("distance_m") is not None
            and row["distance_m"] <= self.radius_meters
        ]
        warnings = []
        sources = ["amap_poi"] if pois else ["agent_no_poi"]
        if not geo:
            warnings.append("缺少 geocode 结果，无法确认候选点坐标。")
        if not pois:
            warnings.append("缺少 poi_search 结果，redline_check 未获得真实敏感场所证据。")
        nearest = min(
            (row.get("distance_m") for row in pois if self._is_sensitive(row) and row.get("distance_m") is not None),
            default=None,
        )
        risk_level = "high" if sensitive else "low" if pois else "unknown"
        data = {
            "redline_radius_meters": self.radius_meters,
            "risk_level": risk_level,
            "violations": [self._normalize_violation(row) for row in sensitive],
            "nearest_sensitive_place_distance_meters": nearest,
            "sensitive_within_200m": sensitive,
        }
        context["redline"] = data
        if sensitive:
            return self.success(
                f"200m 内发现 {len(sensitive)} 个红线敏感对象，建议人工核实边界距离",
                data=data,
                confidence=0.75,
                sources=sources,
                warnings=warnings + ["红线风险必须现场复核距离和当地政策。"],
            )
        return self.success(
            "200m 内未发现学校、幼儿园、中学、政府机构等红线风险" if pois else "红线风险未知，缺少真实 POI 数据",
            data=data,
            confidence=0.45 if not pois else 0.8,
            sources=sources,
            warnings=warnings,
        )

    @classmethod
    def _is_sensitive(cls, row: dict) -> bool:
        text = f"{row.get('name', '')} {row.get('category', '')} {row.get('type', '')} {row.get('type_code', '')}"
        return row.get("category") in cls.sensitive_categories or any(keyword in text for keyword in cls.sensitive_keywords)

    @staticmethod
    def _normalize_violation(row: dict) -> dict:
        return {
            "name": row.get("name"),
            "type": row.get("category") or row.get("type_code"),
            "distance_meters": row.get("distance_m"),
            "address": row.get("address"),
            "source": row.get("source") or "amap",
        }
