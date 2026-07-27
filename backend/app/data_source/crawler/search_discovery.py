from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from app.data_source.crawler.base import CrawlerSettings
from app.models import SiteProjectRecord


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str | None = None
    snippet: str | None = None
    query: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "query": self.query,
        }


class SearchDiscoveryClient:
    """公开网页搜索发现。

    第一版只使用 DuckDuckGo HTML 搜索结果页，不登录、不绕验证码、不访问付费墙。
    测试中通过 fake client 注入，避免依赖真实外网。
    """

    async def discover(
        self,
        query: str,
        *,
        max_results: int,
        timeout_seconds: int,
    ) -> list[SearchResult]:
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; esports-site-selection/1.0; +https://example.com)",
                },
            )
            response.raise_for_status()
        return _parse_duckduckgo_html(response.text, query=query, max_results=max_results)


def build_search_queries(project: SiteProjectRecord, payload: dict[str, Any]) -> list[str]:
    city = project.city or ""
    district = project.district or ""
    project_address = project.address or ""
    name = str(payload.get("name") or "").strip()
    address = str(payload.get("address") or project_address or "").strip()
    task_type = payload.get("task_type")
    base_location = " ".join(part for part in (city, district, address) if part).strip()

    if task_type == "competitor":
        target = " ".join(part for part in (base_location, name) if part).strip()
        return _dedupe(
            [
                f"{target} 价格",
                f"{target} 营业时间",
                f"{target} 机器配置",
            ]
        )

    if task_type == "supporting":
        target = " ".join(part for part in (base_location, name) if part).strip()
        return _dedupe(
            [
                f"{target} 营业时间",
                f"{target} 评分",
            ]
        )

    if task_type == "rent":
        expected_area = _expected_area(project)
        return _dedupe(
            [
                f"{city} {district} {project_address} 商铺出租 {expected_area}平",
                f"{city} {project_address} 商铺租金",
                f"{city} {project_address} 电竞馆 商铺 转让",
            ]
        )

    return []


async def discover_urls_for_payload(
    project: SiteProjectRecord,
    payload: dict[str, Any],
    *,
    settings: CrawlerSettings,
    client: SearchDiscoveryClient,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], str | None]:
    if not settings.search_enabled:
        return [], [], [], "爬虫搜索发现未启用"
    if settings.search_provider != "duckduckgo_html":
        return [], [], [], f"当前仅支持 duckduckgo_html 搜索 Provider：{settings.search_provider}"

    queries = build_search_queries(project, payload)
    discovered: list[SearchResult] = []
    errors: list[str] = []
    seen: set[str] = set()

    for query in queries:
        try:
            results = await client.discover(
                query,
                max_results=max(1, settings.search_max_results),
                timeout_seconds=max(3, settings.search_timeout_seconds),
            )
        except Exception as exc:
            errors.append(f"{query}: {exc}")
            continue
        for result in results:
            normalized_url = _normalize_result_url(result.url)
            if not normalized_url or normalized_url in seen:
                continue
            if not _search_domain_allowed(normalized_url, settings):
                continue
            seen.add(normalized_url)
            discovered.append(
                SearchResult(
                    url=normalized_url,
                    title=result.title,
                    snippet=result.snippet,
                    query=result.query or query,
                )
            )
            if len(discovered) >= settings.search_max_results:
                break
        if len(discovered) >= settings.search_max_results:
            break

    payloads = [
        {
            **payload,
            "url": result.url,
            "discovered_by_search": True,
            "search_query": result.query,
            "search_result": result.model_dump(),
        }
        for result in discovered
    ]
    error_message = "；".join(errors) if errors else None
    return payloads, queries, [item.model_dump() for item in discovered], error_message


def _parse_duckduckgo_html(text: str, *, query: str, max_results: int) -> list[SearchResult]:
    links: list[SearchResult] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
        raw_url = html.unescape(match.group(1))
        normalized = _normalize_result_url(raw_url)
        if not normalized or normalized in seen:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(2))
        links.append(SearchResult(url=normalized, title=html.unescape(title).strip(), query=query))
        seen.add(normalized)
        if len(links) >= max_results:
            return links

    for raw_url in re.findall(r'href="([^"]+)"', text, flags=re.I):
        normalized = _normalize_result_url(html.unescape(raw_url))
        if not normalized or normalized in seen:
            continue
        links.append(SearchResult(url=normalized, query=query))
        seen.add(normalized)
        if len(links) >= max_results:
            break
    return links


def _normalize_result_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    url = html.unescape(raw_url).strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            url = unquote(target)
            parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _search_domain_allowed(url: str, settings: CrawlerSettings) -> bool:
    domain = (urlparse(url).netloc or "").lower()
    if not domain:
        return False
    if any(domain == item or domain.endswith("." + item) for item in settings.blocked_domains):
        return False
    if settings.search_allowed_domains and not any(
        domain == item or domain.endswith("." + item) for item in settings.search_allowed_domains
    ):
        return False
    return True


def _expected_area(project: SiteProjectRecord) -> str:
    raw = project.raw_data if isinstance(project.raw_data, dict) else {}
    value = raw.get("expected_area_sqm")
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "500"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        normalized = " ".join(item.split())
        if normalized and normalized not in result:
            result.append(normalized)
    return result
