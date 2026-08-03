from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.data_source.crawler import service as crawler_service
from app.data_source.crawler.service import process_crawl_task_ids, queue_manual_url_crawl_task


def _project(client, name="Phase16验收") -> str:
    response = client.post("/api/projects", json={
        "name": name, "city": "西安市", "district": "雁塔区", "address": "小寨地铁站",
        "longitude": 108.94, "latitude": 34.22, "radius_meters": 1000, "business_type": "电竞馆",
    })
    assert response.status_code == 200
    return response.json()["project_id"]


class EvidenceCrawler:
    async def crawl(self, url: str, timeout_seconds: int):
        return SimpleNamespace(
            markdown="证据电竞馆 营业时间 10:00-02:00 价格 12 元 机器 120 台 面积 800 平方米",
            html='<script type="application/ld+json">{"@type":"LocalBusiness","openingHours":"10:00-02:00"}</script>',
        )


def test_field_suggestion_review_and_task_retry(client, monkeypatch):
    project_id = _project(client)
    monkeypatch.setenv("CRAWLER_ENABLED", "true")
    monkeypatch.setenv("CRAWLER_ALLOWED_DOMAINS", "example.com")
    get_settings.cache_clear()
    monkeypatch.setattr(crawler_service, "Crawl4AIClient", lambda: EvidenceCrawler())
    with SessionLocal() as db:
        queued = queue_manual_url_crawl_task(
            db, project_id, task_type="competitor", name="证据电竞馆", address="小寨",
            url="https://example.com/shop/1",
        )
    asyncio.run(process_crawl_task_ids(queued["task_ids"]))

    suggestions = client.get(f"/api/projects/{project_id}/crawler-suggestions")
    assert suggestions.status_code == 200
    items = suggestions.json()["items"]
    assert items
    assert all(item["status"] == "pending_review" for item in items)
    accepted = client.post(
        f"/api/projects/{project_id}/crawler-suggestions/{items[0]['id']}/review",
        json={"action": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    retry = client.post(f"/api/projects/{project_id}/crawl/tasks/{queued['task_ids'][0]}/retry")
    assert retry.status_code == 200
    assert retry.json()["task_ids"][0] != queued["task_ids"][0]


def test_business_outcome_confirm_creates_case_memory(client):
    project_id = _project(client, "真实经营反馈")
    saved = client.put(f"/api/projects/{project_id}/business-outcome", json={
        "actual_monthly_rent": 32000,
        "actual_area_sqm": 520,
        "actual_machine_count": 180,
        "occupancy_rate": 0.62,
        "result_status": "operating",
        "success_reasons": ["交通便利"],
        "failure_reasons": [],
        "notes": "来源为投资人月度复盘",
    })
    assert saved.status_code == 200
    assert saved.json()["status"] == "pending_review"

    confirmed = client.post(f"/api/projects/{project_id}/business-outcome/review", json={"status": "confirmed"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    context = client.get(f"/api/projects/{project_id}/memory/context").json()["items"]
    assert any(item["memory_type"] == "case_feedback" and item["source"] == "business_outcome" for item in context)
