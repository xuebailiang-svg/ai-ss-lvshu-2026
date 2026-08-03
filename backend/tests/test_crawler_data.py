from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.data_source.crawler import service as crawler_service
from app.data_source.crawler.service import (
    enrich_project_with_crawler,
    process_crawl_task_ids,
    queue_manual_url_crawl_task,
    queue_project_crawler_tasks,
)
from app.data_source.crawler.worker import CrawlerWorker
from app.models import CrawlTaskRecord, FoodBusinessRecord, RentDataRecord, UnifiedCompetitorRecord


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
        return SimpleNamespace(
            markdown=(
                "测试电竞馆 小寨地铁站 商铺出租 "
                "营业时间 10:00-02:00 价格 12 会员价 10 机器 120 "
                "面积 800 上座率 75% 月租 30000 单价 60"
            )
        )


class FakeDiscovery:
    def __init__(self):
        self.queries: list[str] = []

    async def discover(self, query: str, *, max_results: int, timeout_seconds: int):
        from app.data_source.crawler.search_discovery import SearchResult

        self.queries.append(query)
        return [SearchResult(url="https://example.com/discovered/1", title=f"{query} 详情", query=query)]


class FakeEmptyDiscovery:
    async def discover_provider(self, provider: str, query: str, *, max_results: int, timeout_seconds: int):
        return []


class FakeEmptyCrawler:
    async def crawl(self, url: str, timeout_seconds: int):
        return SimpleNamespace(markdown="这是一段没有经营字段的普通网页内容")


class FakeIrrelevantDiscovery:
    async def discover_provider(self, provider: str, query: str, *, max_results: int, timeout_seconds: int):
        from app.data_source.crawler.search_discovery import SearchResult

        return [
            SearchResult(
                url="https://baike.baidu.com/item/xian",
                title="西安市_百度百科",
                snippet="西安市是陕西省省会，介绍城市面积和历史。",
                query=query,
                provider=provider,
            )
        ]


class FakeMultiDiscovery:
    async def discover_provider(self, provider: str, query: str, *, max_results: int, timeout_seconds: int):
        from app.data_source.crawler.search_discovery import SearchResult

        return [
            SearchResult(url="https://example.com/wrong", title="测试电竞馆 价格详情", snippet="测试电竞馆 小寨", query=query, provider=provider),
            SearchResult(url="https://example.com/right", title="测试电竞馆 营业时间", snippet="测试电竞馆 小寨", query=query, provider=provider),
        ]


class FakeFallbackCrawler:
    async def crawl(self, url: str, timeout_seconds: int):
        if url.endswith("/wrong"):
            return SimpleNamespace(markdown="这是一个不包含目标名称的普通页面 价格 99")
        return SimpleNamespace(markdown="测试电竞馆 小寨 营业时间 10:00-02:00 价格 12 机器 120")


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


def test_crawler_search_empty_records_diagnostics(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        db.add(
            UnifiedCompetitorRecord(
                project_id=project_id,
                name="无搜索结果竞品",
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
                discovery_client=FakeEmptyDiscovery(),
            )
        )

        assert result["skipped_count"] == 1
        task = db.query(CrawlTaskRecord).filter(CrawlTaskRecord.project_id == project_id).first()
        assert task is not None
        assert task.status == "skipped"
        assert task.result_snapshot["search_queries"]
        assert task.result_snapshot["search_errors"]
        assert task.result_snapshot["search_errors"][0]["error_type"] == "parse_empty"


def test_crawler_search_rejects_irrelevant_city_page_without_mutating_competitor(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        row = UnifiedCompetitorRecord(
            project_id=project_id,
            name="测试电竞馆",
            address="小寨地铁站",
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
                discovery_client=FakeIrrelevantDiscovery(),
            )
        )

        assert result["skipped_count"] == 1
        saved = db.get(UnifiedCompetitorRecord, row_id)
        assert saved is not None
        assert saved.hour_price is None
        assert saved.area_sqm is None
        assert not saved.raw_data.get("crawler_detail")
        task = db.query(CrawlTaskRecord).filter(CrawlTaskRecord.project_id == project_id).first()
        assert task.status == "skipped"
        assert task.result_snapshot["search_results"][0]["eligible"] is False
        assert task.result_snapshot["search_errors"][0]["error_type"] == "irrelevant_result"


def test_crawler_rent_rejects_irrelevant_city_page_without_creating_record(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        result = asyncio.run(
            enrich_project_with_crawler(
                db,
                project_id=project_id,
                types=["rent"],
                max_items=1,
                client=FakeCrawler(),
                discovery_client=FakeIrrelevantDiscovery(),
            )
        )

        assert result["skipped_count"] == 1
        assert db.query(RentDataRecord).filter(RentDataRecord.project_id == project_id).count() == 0


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
        db.add(
            RentDataRecord(
                project_id=project_id,
                monthly_rent=30000,
                area_sqm=500,
                rent_per_sqm=60,
                location_type="错误租金测试",
                source="crawler",
                confidence=0.5,
                status="rejected",
                raw_data={"crawler_detail": {"monthly_rent": 30000, "area_sqm": 500}},
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
    assert body["crawler_quality"]["rent_crawler_count"] == 0
    assert body["crawler_quality"]["pending_review_count"] == 1


def test_crawler_unknown_project_returns_404(client):
    response = client.get("/api/projects/not-exist/crawl/tasks")

    assert response.status_code == 404


def test_crawler_queue_creates_pending_tasks_without_running(client, monkeypatch):
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

        result = queue_project_crawler_tasks(
            db,
            project_id=project_id,
            types=["competitor"],
            max_items=1,
            discover_urls=True,
        )

        assert result["success"] is True
        assert result["task_count"] == 1
        assert result["task_ids"]
        task = db.get(CrawlTaskRecord, result["task_ids"][0])
        assert task is not None
        assert task.status == "pending"


def test_crawler_queue_only_plans_fields_missing_from_record(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        db.add(UnifiedCompetitorRecord(
            project_id=project_id,
            name="已有价格电竞馆",
            address="小寨",
            hour_price=15,
            machine_count=80,
            source="amap",
            confidence=0.9,
            status="pending_review",
            raw_data={"manual_detail": {"business_hours": "24小时"}},
        ))
        db.commit()
        result = queue_project_crawler_tasks(db, project_id=project_id, types=["competitor"], max_items=1)
        task = db.get(CrawlTaskRecord, result["task_ids"][0])
        assert "hour_price" not in task.input_snapshot["missing_fields"]
        assert "machine_count" not in task.input_snapshot["missing_fields"]
        assert "business_hours" not in task.input_snapshot["missing_fields"]
        assert "member_price" in task.input_snapshot["missing_fields"]


def test_worker_falls_back_to_second_candidate_and_records_attempts(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    monkeypatch.setenv("CRAWLER_SEARCH_MAX_RESULTS", "3")
    get_settings.cache_clear()
    monkeypatch.setattr(crawler_service, "Crawl4AIClient", lambda: FakeFallbackCrawler())
    monkeypatch.setattr(crawler_service, "SearchDiscoveryClient", lambda: FakeMultiDiscovery())
    with SessionLocal() as db:
        db.add(UnifiedCompetitorRecord(
            project_id=project_id,
            name="测试电竞馆",
            address="小寨",
            source="amap",
            confidence=0.9,
            status="pending_review",
            raw_data={},
        ))
        db.commit()
        result = queue_project_crawler_tasks(db, project_id=project_id, types=["competitor"], max_items=1, planning_mode="rules")
        task_id = result["task_ids"][0]

    asyncio.run(process_crawl_task_ids([task_id]))

    with SessionLocal() as db:
        task = db.get(CrawlTaskRecord, task_id)
        assert task.status == "success"
        assert [item["status"] for item in task.result_snapshot["candidate_attempts"]] == ["irrelevant", "accepted"]
        assert task.target_url == "https://example.com/right"


def test_crawler_api_only_queues_for_independent_worker(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        db.add(
            UnifiedCompetitorRecord(
                project_id=project_id,
                name="独立 Worker 测试电竞馆",
                address="测试地址",
                distance_meters=200,
                source="amap",
                confidence=0.9,
                status="pending_review",
                raw_data={"source_url": "https://example.com/shop/worker"},
            )
        )
        db.commit()

    response = client.post(
        f"/api/projects/{project_id}/crawl/enrich",
        json={"types": ["competitor"], "max_items": 1, "discover_urls": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_count"] == 1
    assert "独立 Worker" in body["message"]
    with SessionLocal() as db:
        task = db.get(CrawlTaskRecord, body["task_ids"][0])
        assert task is not None
        assert task.status == "pending"


def test_independent_worker_claims_oldest_pending_task(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    get_settings.cache_clear()
    with SessionLocal() as db:
        first = CrawlTaskRecord(project_id=project_id, task_type="rent", provider="crawl4ai", status="pending")
        second = CrawlTaskRecord(project_id=project_id, task_type="rent", provider="crawl4ai", status="pending")
        db.add_all([first, second])
        db.commit()
        first_id = first.id
        second_id = second.id

    worker = CrawlerWorker()
    claimed_id = worker.claim_next_task()

    assert claimed_id == first_id
    with SessionLocal() as db:
        assert db.get(CrawlTaskRecord, first_id).status == "running"
        assert db.get(CrawlTaskRecord, second_id).status == "pending"


def test_manual_url_task_runs_in_independent_session(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    monkeypatch.setattr(crawler_service, "Crawl4AIClient", lambda: FakeCrawler())

    with SessionLocal() as db:
        result = queue_manual_url_crawl_task(
            db,
            project_id=project_id,
            task_type="competitor",
            name="手动链接电竞馆",
            address="测试地址",
            url="https://example.com/manual/shop",
        )
        task_ids = result["task_ids"]

    asyncio.run(process_crawl_task_ids(task_ids))

    with SessionLocal() as db:
        task = db.get(CrawlTaskRecord, task_ids[0])
        assert task is not None
        assert task.status == "success"
        competitors = db.query(UnifiedCompetitorRecord).filter(
            UnifiedCompetitorRecord.project_id == project_id,
            UnifiedCompetitorRecord.source == "crawler",
        ).all()
        assert len(competitors) == 1
        assert competitors[0].status == "pending_review"
        assert competitors[0].hour_price == 12
        evidence = competitors[0].raw_data["crawler_detail"]["field_evidence"]
        assert any(item["field"] == "hour_price" and item["source_url"] == "https://example.com/manual/shop" for item in evidence)

    response = client.get(f"/api/projects/{project_id}/competitors")
    suggestion = response.json()["items"][0]["crawler_suggestion"]
    assert suggestion["review_status"] == "pending_review"
    assert suggestion["source_domain"] == "example.com"
    assert suggestion["field_evidence"]


def test_manual_url_supporting_task_creates_pending_food_record(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    monkeypatch.setattr(crawler_service, "Crawl4AIClient", lambda: FakeCrawler())

    with SessionLocal() as db:
        result = queue_manual_url_crawl_task(
            db,
            project_id=project_id,
            task_type="supporting",
            record_type="food",
            name="手动链接餐饮",
            address="测试地址",
            url="https://example.com/manual/food",
        )
        task_ids = result["task_ids"]

    asyncio.run(process_crawl_task_ids(task_ids))

    with SessionLocal() as db:
        task = db.get(CrawlTaskRecord, task_ids[0])
        assert task is not None
        assert task.status == "success"
        rows = db.query(FoodBusinessRecord).filter(
            FoodBusinessRecord.project_id == project_id,
            FoodBusinessRecord.source == "crawler",
        ).all()
        assert len(rows) == 1
        assert rows[0].status == "pending_review"
        assert rows[0].raw_data["crawler_detail"]["source_url"] == "https://example.com/manual/food"


def test_manual_url_task_with_no_extracted_fields_is_skipped(client, monkeypatch):
    project_id = _create_project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    monkeypatch.setattr(crawler_service, "Crawl4AIClient", lambda: FakeEmptyCrawler())

    with SessionLocal() as db:
        result = queue_manual_url_crawl_task(
            db,
            project_id=project_id,
            task_type="competitor",
            name="无字段页面",
            address="测试地址",
            url="https://example.com/manual/empty",
        )
        task_ids = result["task_ids"]

    asyncio.run(process_crawl_task_ids(task_ids))

    with SessionLocal() as db:
        task = db.get(CrawlTaskRecord, task_ids[0])
        assert task is not None
        assert task.status == "skipped"
        assert "未识别到可用" in task.error_message
        assert task.result_snapshot["extracted_fields"] == {}
