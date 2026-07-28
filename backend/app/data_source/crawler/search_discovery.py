from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from app.data_source.crawler.base import CrawlerSettings
from app.models import SiteProjectRecord


def _search_error(provider: str, query: str, error_type: str, message: str) -> dict[str, str]:
    return {
        "provider": provider,
        "query": query,
        "error_type": error_type,
        "message": message,
    }


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str | None = None
    snippet: str | None = None
    query: str | None = None
    provider: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "query": self.query,
            "provider": self.provider,
        }


class SearchDiscoveryClient:
    """公开网页搜索发现。

    不登录、不处理验证码、不绕过反爬或付费墙。测试可注入 fake client。
    """

    async def discover(
        self,
        query: str,
        *,
        max_results: int,
        timeout_seconds: int,
    ) -> list[SearchResult]:
        return await self.discover_provider(
            "duckduckgo_html",
            query,
            max_results=max_results,
            timeout_seconds=timeout_seconds,
        )

    async def discover_provider(
        self,
        provider: str,
        query: str,
        *,
        max_results: int,
        timeout_seconds: int,
    ) -> list[SearchResult]:
        provider = provider.strip().lower()
        if provider == "duckduckgo_html":
            return await self._discover_duckduckgo(query, max_results=max_results, timeout_seconds=timeout_seconds)
        if provider == "bing_html":
            return await self._discover_bing(query, max_results=max_results, timeout_seconds=timeout_seconds)
        raise ValueError(f"不支持的搜索 Provider: {provider}")

    async def _get_text(self, url: str, *, timeout_seconds: int) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        }
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"HTTP {response.status_code}") from exc
        return response.text

    async def _discover_duckduckgo(self, query: str, *, max_results: int, timeout_seconds: int) -> list[SearchResult]:
        text = await self._get_text(
            f"https://duckduckgo.com/html/?q={quote_plus(query)}",
            timeout_seconds=timeout_seconds,
        )
        return _parse_duckduckgo_html(text, query=query, max_results=max_results)

    async def _discover_bing(self, query: str, *, max_results: int, timeout_seconds: int) -> list[SearchResult]:
        text = await self._get_text(
            f"https://www.bing.com/search?q={quote_plus(query)}",
            timeout_seconds=timeout_seconds,
        )
        return _parse_bing_html(text, query=query, max_results=max_results)


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
        return _dedupe([f"{target} 价格", f"{target} 营业时间", f"{target} 机器配置"])

    if task_type == "supporting":
        target = " ".join(part for part in (base_location, name) if part).strip()
        return _dedupe([f"{target} 营业时间", f"{target} 评分"])

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
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], str | None, list[dict[str, str]]]:
    if not settings.search_enabled:
        return [], [], [], "爬虫搜索发现未启用", [
            _search_error("system", "", "disabled", "爬虫搜索发现未启用")
        ]

    providers = _provider_list(settings.search_provider)
    queries = build_search_queries(project, payload)
    discovered: list[SearchResult] = []
    errors: list[str] = []
    search_errors: list[dict[str, str]] = []
    seen: set[str] = set()
    filtered_count = 0

    for query in queries:
        for provider in providers:
            try:
                if hasattr(client, "discover_provider"):
                    results = await client.discover_provider(
                        provider,
                        query,
                        max_results=max(1, settings.search_max_results),
                        timeout_seconds=max(3, settings.search_timeout_seconds),
                    )
                else:
                    results = await client.discover(
                        query,
                        max_results=max(1, settings.search_max_results),
                        timeout_seconds=max(3, settings.search_timeout_seconds),
                    )
            except Exception as exc:
                error_type = _classify_search_exception(exc)
                message = f"{provider} {query}: {exc}"
                errors.append(message)
                search_errors.append(_search_error(provider, query, error_type, str(exc)))
                continue

            if not results:
                message = f"{provider} {query}: 未解析到搜索结果"
                errors.append(message)
                search_errors.append(_search_error(provider, query, "parse_empty", "未解析到搜索结果"))
                continue

            for result in results:
                normalized_url = _normalize_result_url(result.url)
                if not normalized_url or normalized_url in seen:
                    continue
                if not _search_domain_allowed(normalized_url, settings):
                    filtered_count += 1
                    search_errors.append(
                        _search_error(result.provider or provider, result.query or query, "domain_filtered", normalized_url)
                    )
                    continue
                seen.add(normalized_url)
                discovered.append(
                    SearchResult(
                        url=normalized_url,
                        title=result.title,
                        snippet=result.snippet,
                        query=result.query or query,
                        provider=result.provider or provider,
                    )
                )
                if len(discovered) >= settings.search_max_results:
                    break
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
    if discovered:
        return payloads, queries, [item.model_dump() for item in discovered], None, search_errors

    error_message = "；".join(errors)
    if filtered_count:
        extra = f"域名过滤后无可用结果，过滤 {filtered_count} 个"
        error_message = f"{error_message}；{extra}" if error_message else extra
    return payloads, queries, [], error_message or "未发现可抓取的公开网页", search_errors


def _classify_search_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "http_error"
    if isinstance(exc, httpx.RequestError):
        return "request_error"
    if isinstance(exc, ValueError):
        return "unsupported_provider"
    return "failed"


def _parse_duckduckgo_html(text: str, *, query: str, max_results: int) -> list[SearchResult]:
    links: list[SearchResult] = []
    seen: set[str] = set()
    for match in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.I | re.S):
        raw_url = html.unescape(match.group(1))
        normalized = _normalize_result_url(raw_url)
        if not normalized or normalized in seen:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(2))
        links.append(SearchResult(url=normalized, title=html.unescape(title).strip(), query=query, provider="duckduckgo_html"))
        seen.add(normalized)
        if len(links) >= max_results:
            return links

    for raw_url in re.findall(r'href="([^"]+)"', text, flags=re.I):
        normalized = _normalize_result_url(html.unescape(raw_url))
        if not normalized or normalized in seen:
            continue
        links.append(SearchResult(url=normalized, query=query, provider="duckduckgo_html"))
        seen.add(normalized)
        if len(links) >= max_results:
            break
    return links


def _parse_bing_html(text: str, *, query: str, max_results: int) -> list[SearchResult]:
    links: list[SearchResult] = []
    seen: set[str] = set()
    for block in re.findall(r'<li[^>]+class="b_algo"[^>]*>(.*?)</li>', text, flags=re.I | re.S):
        match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
        if not match:
            continue
        normalized = _normalize_result_url(html.unescape(match.group(1)))
        if not normalized or normalized in seen:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(2))
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)) if snippet_match else None
        links.append(
            SearchResult(
                url=normalized,
                title=html.unescape(title).strip(),
                snippet=html.unescape(snippet).strip() if snippet else None,
                query=query,
                provider="bing_html",
            )
        )
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


def _provider_list(raw: str | None) -> list[str]:
    providers = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    return providers or ["duckduckgo_html"]


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        normalized = " ".join(item.split())
        if normalized and normalized not in result:
            result.append(normalized)
    return result
