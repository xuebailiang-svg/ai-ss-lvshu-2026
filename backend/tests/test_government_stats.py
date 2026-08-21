from __future__ import annotations

import asyncio
import io

import httpx
from openpyxl import Workbook
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.data_model import RegionalStatisticData
from app.data_source.base import DataSourceRequest, ProviderCallStatus
from app.data_source.government_stats.parser import parse_official_text, parse_structured_rows
from app.data_source.government_stats.provider import GovernmentStatsProvider
from app.data_source.government_stats.adapters import XianStatsAdapter
from app.data_source.government_stats.service import (
    _upsert_statistic,
    city_insight,
    save_uploaded_statistics,
)
from app.data_source.government_stats.upload import parse_csv_upload, parse_pdf_upload, parse_xlsx_upload
from app.llm.prompts import SITE_SELECTION_REPORT_PROMPT
from app.llm.service import build_ai_input
from app.models import RegionalStatisticRecord, SiteProjectRecord


PROJECT = {
    "name": "小寨电竞馆选址",
    "city": "西安市",
    "district": "雁塔区",
    "address": "小寨地铁站",
    "longitude": 108.946767,
    "latitude": 34.222838,
    "radius_meters": 1000,
    "business_type": "电竞馆",
}


def create_project(client) -> str:
    response = client.post("/api/projects", json=PROJECT)
    assert response.status_code == 200
    return response.json()["project_id"]


def statistic(
    metric_code: str,
    metric_name: str,
    value: float,
    *,
    scope_level: str = "city",
    scope_code: str = "610100",
    scope_name: str = "西安市",
    status: str = "confirmed",
) -> RegionalStatisticData:
    return RegionalStatisticData(
        metric_code=metric_code,
        metric_name=metric_name,
        value_numeric=value,
        unit="万人" if metric_code == "resident_population" else "亿元",
        scope_level=scope_level,
        scope_code=scope_code,
        scope_name=scope_name,
        stat_period="2025",
        source_name="西安市统计局",
        source_url="https://tjj.xa.gov.cn/example.html",
        source_format="html",
        source="government_stats",
        status=status,
        confidence=.85,
    )


def test_official_html_parser_extracts_period_units_and_age_structure():
    text = """
    西安市2025年国民经济和社会发展统计公报。
    年末全市常住人口1316.76万人，城镇化率为80.5%。
    地区生产总值达到12000.5亿元，第三产业增加值占地区生产总值比重为65.2%。
    社会消费品零售总额完成5000亿元，居民人均可支配收入达到52000元。
    0—14岁人口占全市人口的比重为15.1%，65岁及以上人口占全市人口的比重为14.2%。
    """
    items = parse_official_text(
        text,
        scope_level="city",
        scope_code="610100",
        scope_name="西安市",
        source_name="西安市统计局",
        source_url="https://tjj.xa.gov.cn/example.html",
        source_format="html",
    )
    by_code = {item.metric_code: item for item in items}

    assert by_code["resident_population"].value_numeric == 1316.76
    assert by_code["resident_population"].unit == "万人"
    assert by_code["gdp"].value_numeric == 12000.5
    assert by_code["tertiary_industry_share"].value_numeric == 65.2
    assert by_code["population_age_structure"].stat_period == "2025"
    assert "65岁及以上14.2%" in (by_code["population_age_structure"].value_text or "")
    assert all(item.scope_level == "city" for item in items)
    assert all(item.status == "confirmed" for item in items)


def test_official_json_rows_are_strictly_parsed_without_guessing():
    items, errors = parse_structured_rows(
        [
            {
                "metric_code": "resident_population",
                "metric_name": "常住人口",
                "value_numeric": "1,323.63",
                "unit": "万人",
                "scope_level": "city",
                "scope_code": "610100",
                "scope_name": "西安市",
                "stat_period": "2025",
            },
            {"metric_code": "gdp", "metric_name": "地区生产总值"},
        ],
        source_name="国家数据",
        source_url="https://data.stats.gov.cn/api/example",
    )

    assert len(items) == 1
    assert items[0].value_numeric == 1323.63
    assert items[0].confidence == .95
    assert errors[0]["row"] == 2
    assert "缺少字段" in errors[0]["reason"]


def test_pdf_parser_result_is_pending_review():
    items = parse_official_text(
        "陕西省2024年统计公报，全省常住人口3953万人，地区生产总值达到35538亿元。",
        scope_level="province",
        scope_code="610000",
        scope_name="陕西省",
        source_name="陕西省统计局",
        source_url="https://tjj.shaanxi.gov.cn/example.pdf",
        source_format="pdf",
    )

    assert items
    assert all(item.status == "pending_review" for item in items)
    assert all(item.confidence == .75 for item in items)


def test_xian_adapter_discovers_latest_official_html_and_parses_it():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/1.html"):
            return httpx.Response(
                200,
                text='<a href="/stats/2025.html">西安市2025年国民经济和社会发展统计公报</a>',
                request=request,
            )
        return httpx.Response(
            200,
            text="<h1>西安市2025年国民经济和社会发展统计公报</h1><p>年末全市常住人口1323.63万人。</p>",
            request=request,
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await XianStatsAdapter(client).collect()

    items, warnings = asyncio.run(run())

    assert warnings == []
    assert items[0].metric_code == "resident_population"
    assert items[0].value_numeric == 1323.63
    assert items[0].source_name == "西安市统计局"


def test_csv_upload_aliases_and_duplicate_sync_upsert():
    content = (
        "指标编码,指标名称,数值,单位,范围层级,行政区代码,行政区名称,统计期\n"
        "resident_population,常住人口,1316.76,万人,city,610100,西安市,2025\n"
    ).encode("utf-8")
    items, errors = parse_csv_upload(
        content,
        source_name="西安市统计局",
        source_url="https://tjj.xa.gov.cn/upload.xlsx",
    )
    assert errors == []
    assert items[0].source == "government_stats"

    with SessionLocal() as db:
        save_uploaded_statistics(db, items)
        save_uploaded_statistics(db, items)
        rows = db.query(RegionalStatisticRecord).all()
    assert len(rows) == 1
    assert rows[0].value_numeric == 1316.76


def test_xlsx_upload_parses_structured_official_rows():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["指标编码", "指标名称", "数值", "单位", "范围层级", "行政区代码", "行政区名称", "统计期"])
    sheet.append(["gdp", "地区生产总值", 12000.5, "亿元", "city", "610100", "西安市", "2025"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    items, errors = parse_xlsx_upload(
        buffer.getvalue(),
        source_name="西安市统计局",
        source_url="https://tjj.xa.gov.cn/official.xlsx",
    )

    assert errors == []
    assert items[0].metric_code == "gdp"
    assert items[0].confidence == .95


def test_pdf_upload_is_low_confidence_and_pending(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "西安市2025年统计公报，全市常住人口1316.76万人。"

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    items, errors = parse_pdf_upload(
        b"fake-pdf",
        source_name="西安市统计局",
        source_url="https://tjj.xa.gov.cn/official.pdf",
        scope_level="city",
        scope_code="610100",
        scope_name="西安市",
        stat_period="2025",
    )

    assert errors == []
    assert items[0].status == "pending_review"
    assert items[0].confidence == .75


def test_city_insight_separates_macro_trade_area_and_lbs_gap(client):
    project_id = create_project(client)
    with SessionLocal() as db:
        save_uploaded_statistics(db, [
            statistic("resident_population", "常住人口", 1316.76),
            statistic("gdp", "地区生产总值", 12000.5),
        ])
        project = db.query(SiteProjectRecord).filter_by(project_id=project_id).one()
        result = city_insight(db, project)

    assert result["macro_context"]["population"]["city"][0]["scope_name"] == "西安市"
    assert result["trade_area_context"]["scope"]["radius_meters"] == 1000
    assert "不是政府宏观统计" in result["trade_area_context"]["scope"]["note"]
    assert result["lbs_context"]["available"] is False
    assert "小时客流" in result["lbs_context"]["missing"]
    assert "不使用城市宏观数据推算1km" in result["lbs_context"]["message"]
    assert result["data_quality"]["coverage_status"] == "target_ready"
    assert result["data_quality"]["confirmed_target_metric_count"] == 2
    assert result["data_quality"]["fallback_metric_count"] == 0


def test_city_insight_marks_province_and_country_data_as_fallback_only(client):
    project_id = create_project(client)
    with SessionLocal() as db:
        save_uploaded_statistics(db, [
            statistic(
                "resident_population",
                "常住人口",
                3952,
                scope_level="province",
                scope_code="610000",
                scope_name="陕西省",
            ),
            statistic(
                "gdp",
                "国内生产总值",
                1400000,
                scope_level="country",
                scope_code="100000",
                scope_name="全国",
            ),
        ])
        project = db.query(SiteProjectRecord).filter_by(project_id=project_id).one()
        result = city_insight(db, project)

    quality = result["data_quality"]
    assert result["status"] == "ready"
    assert quality["coverage_status"] == "fallback_only"
    assert quality["confirmed_target_metric_count"] == 0
    assert quality["fallback_metric_count"] == 2
    assert quality["fallback_scope_names"] == ["全国", "陕西省"]
    assert quality["missing_target_scopes"] == ["西安市", "雁塔区"]
    assert "不得将上级行政区数据描述为项目所在城市" in quality["scope_warning"]


def test_pending_and_rejected_statistics_do_not_enter_city_insight_or_ai(client):
    project_id = create_project(client)
    with SessionLocal() as db:
        _upsert_statistic(db, statistic("resident_population", "常住人口", 999, status="pending_review"))
        _upsert_statistic(db, statistic("gdp", "地区生产总值", 888, status="rejected"))
        db.commit()
        project = db.query(SiteProjectRecord).filter_by(project_id=project_id).one()
        result = city_insight(db, project)
        ai_input = build_ai_input(db, project_id).model_dump(mode="python")

    assert result["data_quality"]["confirmed_metric_count"] == 0
    assert ai_input["city_insight"]["macro_context"]["population"] == {}
    assert ai_input["city_insight"]["macro_context"]["economy"] == {}


def test_collect_endpoint_uses_cache_without_external_network(client):
    project_id = create_project(client)
    with SessionLocal() as db:
        save_uploaded_statistics(db, [statistic("resident_population", "常住人口", 1316.76)])

    response = client.post(f"/api/projects/{project_id}/collect/government-stats")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["confirmed_metric_count"] == 1
    assert response.json()["latest_period"] == "2025"


def test_government_macro_context_does_not_change_project_quality_score(client):
    project_id = create_project(client)
    before = client.get(f"/api/projects/{project_id}/data-quality").json()
    with SessionLocal() as db:
        save_uploaded_statistics(db, [
            statistic("resident_population", "常住人口", 1316.76),
            statistic("gdp", "地区生产总值", 12000.5),
        ])
    after = client.get(f"/api/projects/{project_id}/data-quality").json()

    assert before["quality_score"] == after["quality_score"]
    assert "regional_context_quality" not in after


def test_government_provider_mock_adapter_returns_unified_data(monkeypatch):
    async def fake_collect(self):
        return [statistic("gdp", "地区生产总值", 12000.5)], []

    monkeypatch.setattr(
        "app.data_source.government_stats.adapters.OfficialStatisticsAdapter.collect",
        fake_collect,
    )
    monkeypatch.setattr(GovernmentStatsProvider, "_source_keys", lambda self, request=None: ["xian"])
    result = asyncio.run(
        GovernmentStatsProvider().get_statistics(
            DataSourceRequest(city="西安市", categories=["xian"])
        )
    )

    assert result.status == ProviderCallStatus.success
    assert result.items[0].metric_code == "gdp"
    assert result.items[0].source == "government_stats"


def test_report_prompt_contains_city_scope_truthfulness_rules():
    assert "## 三、城市与区域背景" in SITE_SELECTION_REPORT_PROMPT
    assert "## 四、商圈微观环境" in SITE_SELECTION_REPORT_PROMPT
    assert "## 六、客群与客流数据" in SITE_SELECTION_REPORT_PROMPT
    assert "## 十一、数据口径、记忆与来源" in SITE_SELECTION_REPORT_PROMPT
    assert "未接入真实客流数据" in SITE_SELECTION_REPORT_PROMPT
    assert "禁止根据政府宏观数据推测 1km" in SITE_SELECTION_REPORT_PROMPT
