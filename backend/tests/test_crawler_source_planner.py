from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.data_source.crawler.source_planner import (
    build_ai_source_plan,
    build_rule_source_plan,
    rank_real_candidates,
)


PROJECT = SimpleNamespace(
    city="西安市",
    district="雁塔区",
    address="小寨地铁站",
    business_type="电竞馆",
    expected_area_sqm=500,
)


class FakeLLM:
    def __init__(self, content: str):
        self.content = content

    def generate_chat(self, chat_input, prompt):
        return SimpleNamespace(content=self.content, model="fake-model")


def test_rule_plan_selects_business_specific_sources():
    plan = build_rule_source_plan(PROJECT, {"task_type": "rent", "address": "小寨地铁站"})

    assert plan["search_queries"]
    assert "商铺出租" in plan["search_queries"][0]
    assert plan["strategies"][0]["source_type"] == "property_listing"
    assert "monthly_rent" in plan["missing_fields"]


def test_ai_plan_can_change_queries_but_not_supply_final_url():
    plan = asyncio.run(build_ai_source_plan(
        PROJECT,
        {"task_type": "competitor", "name": "测试电竞馆", "address": "小寨"},
        client=FakeLLM('{"search_queries":["西安 测试电竞馆 机位 价格"],"preferred_source_types":["merchant_detail"],"preferred_domains":["dianping.com"],"reason":"优先门店详情"}'),
    ))

    assert plan["mode"] == "ai_assisted"
    assert plan["search_queries"][0] == "西安 测试电竞馆 机位 价格 site:dianping.com"
    assert "西安 测试电竞馆 机位 价格" in plan["search_queries"]
    assert "url" not in plan


def test_ai_ranking_discards_invented_urls():
    candidates = [
        {"url": "https://example.com/a", "title": "测试电竞馆详情"},
        {"url": "https://example.com/b", "title": "测试电竞馆价格"},
    ]
    ranked = asyncio.run(rank_real_candidates(
        PROJECT,
        {"task_type": "competitor", "name": "测试电竞馆"},
        candidates,
        client=FakeLLM('{"ordered_urls":["https://evil.example/fake","https://example.com/b"],"reasons":{}}'),
    ))

    assert ranked["ordered_urls"] == ["https://example.com/b", "https://example.com/a"]
    assert "https://evil.example/fake" not in ranked["ordered_urls"]
