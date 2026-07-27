from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.data_source.crawler.service import enrich_project_with_crawler
from app.models import CrawlTaskRecord, RentDataRecord, UnifiedCompetitorRecord


def _create_project(client) -> str:
    response = client.post(
        "/api/projects",
        json={
            "name": "小寨电竞馆爬虫测试",
            "city": "西安市",
            "district": "雁塔区",
            "address": "小寨地铁站",
            "longitude": 108.946767,
            "latitude": 34.222838,
            "radius_meters": 1000,
            "business_type": "电竞馆",
        },
    )
    assert response.status_code == 200
    return response.json()["project_id"]


class FakeCrawler:
    async def crawl(self, url: str, timeout_seconds: int):
        return SimpleNamespace(markdown="营业时间 10:00-02:00 价格 12 会员价 10 机器 120 面积 800 上座率 75% 月租 30000 单价 60")


class FakeDiscovery:
    def __init__(self):
        self.queries: list[str] = []

    async def discover(self, query: str, *, max_results: int, timeout_seconds: int):
        from app.data_source.crawler.search_discovery import SearchResult

        self.queries.append(query)
        return [SearchResult(url="https://example.com/discovered/1", title="测试公开页面", query=query)]


def test_crawler_enrich_disabled_returns_clear_message(client):
    project_id = _create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/crawl/enrich",
        json={"types": ["competitor"], "max_items": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["task_count"] == 0
    assert "爬虫能力未启用" in body["message"]


def test_crawler_enrich_saves_competitor_detail_with_mock(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    with SessionLocal() as db:
        row = UnifiedCompetitorRecord(
            project_id=project_id,
            name="测试电竞馆",
            address="测试地址",
            distance_meters=300,
            source="amap",
            confidence=0.9,
            status="pending_review",
            raw_data={"source_url": "https://example.com/shop/1"},
        )
        db.add(row)
        db.commit()
        row_id = row.id

        result = asyncio.run(
            enrich_project_with_crawler(
                db,
                project_id=project_id,
                types=["competitor"],
                max_items=1,
                client=FakeCrawler(),
                discover_urls=False,
            )
        )

        assert result["success"] is True
        assert result["completed_count"] == 1
        saved = db.get(UnifiedCompetitorRecord, row_id)
        assert saved is not None
        assert saved.status == "pending_review"
        assert saved.hour_price == 12
        assert saved.member_price == 10
        assert saved.machine_count == 120
        assert saved.raw_data["crawler_detail"]["source_url"] == "https://example.com/shop/1"


def test_crawler_enrich_skips_candidate_without_public_url_when_discovery_disabled(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        db.add(
            UnifiedCompetitorRecord(
                project_id=project_id,
                name="无链接竞品",
                address="测试地址",
                distance_meters=300,
                source="amap",
                confidence=0.9,
                status="pending_review",
                raw_data={},
            )
        )
        db.commit()

        result = asyncio.run(
            enrich_project_with_crawler(
                db,
                project_id=project_id,
                types=["competitor"],
                max_items=1,
                client=FakeCrawler(),
                discover_urls=False,
            )
        )

        assert result["task_count"] == 1
        assert result["skipped_count"] == 1
        task = db.query(CrawlTaskRecord).filter(CrawlTaskRecord.project_id == project_id).first()
        assert task is not None
        assert task.status == "skipped"


def test_crawler_enrich_discovers_url_from_name_and_address(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    discovery = FakeDiscovery()
    with SessionLocal() as db:
        row = UnifiedCompetitorRecord(
            project_id=project_id,
            name="测试电竞馆",
            address="测试地址",
            distance_meters=300,
            source="amap",
            confidence=0.9,
            status="pending_review",
            raw_data={},
        )
        db.add(row)
        db.commit()
        row_id = row.id

        result = asyncio.run(
            enrich_project_with_crawler(
                db,
                project_id=project_id,
                types=["competitor"],
                max_items=1,
                client=FakeCrawler(),
                discovery_client=discovery,
            )
        )

        assert result["task_count"] == 1
        assert result["discovered_url_count"] == 1
        assert result["completed_count"] == 1
        assert discovery.queries
        saved = db.get(UnifiedCompetitorRecord, row_id)
        assert saved is not None
        assert saved.hour_price == 12
        assert saved.raw_data["crawler_detail"]["source_url"] == "https://example.com/discovered/1"
        task = db.query(CrawlTaskRecord).filter(CrawlTaskRecord.project_id == project_id).first()
        assert task.target_url == "https://example.com/discovered/1"
        assert task.input_snapshot["discovered_by_search"] is True


def test_crawler_rent_search_creates_pending_rent_record(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    discovery = FakeDiscovery()
    with SessionLocal() as db:
        result = asyncio.run(
            enrich_project_with_crawler(
                db,
                project_id=project_id,
                types=["rent"],
                max_items=1,
                client=FakeCrawler(),
                discovery_client=discovery,
            )
        )

        assert result["discovered_url_count"] == 1
        assert result["saved"]["rent"] == 1
        rows = db.query(RentDataRecord).filter(RentDataRecord.project_id == project_id).all()
        assert len(rows) == 1
        assert rows[0].source == "crawler"
        assert rows[0].status == "pending_review"
        assert rows[0].monthly_rent == 30000
        assert rows[0].raw_data["crawler_detail"]["source_url"] == "https://example.com/discovered/1"


def test_crawler_quality_is_returned_from_data_quality(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    with SessionLocal() as db:
        db.add(
            UnifiedCompetitorRecord(
                project_id=project_id,
                name="测试电竞馆",
                address="测试地址",
                distance_meters=300,
                source="amap",
                confidence=0.9,
                status="pending_review",
                raw_data={"source_url": "https://example.com/shop/1"},
            )
        )
        db.commit()
        asyncio.run(
            enrich_project_with_crawler(
                db,
                project_id=project_id,
                types=["competitor"],
                max_items=1,
                client=FakeCrawler(),
            )
        )

    response = client.get(f"/api/projects/{project_id}/data-quality")

    assert response.status_code == 200
    body = response.json()
    assert "crawler_quality" in body
    assert body["crawler_quality"]["competitor_crawler_count"] == 1
    assert body["crawler_quality"]["pending_review_count"] == 1


def test_crawler_unknown_project_returns_404(client):
    response = client.get("/api/projects/not-exist/crawl/tasks")

    assert response.status_code == 404
