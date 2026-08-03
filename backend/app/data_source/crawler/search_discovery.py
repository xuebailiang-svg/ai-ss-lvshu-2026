from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from app.data_source.crawler.base import CrawlerSettings
from app.data_source.crawler.source_planner import build_rule_search_queries
from app.models import SiteProjectRecord


LOW_SIGNAL_DOMAINS = {
    "baike.baidu.com",
    "zhihu.com",
    "zhuanlan.zhihu.com",
}
COMPETITOR_TERMS = ("电竞", "网吧", "网咖", "电玩", "游戏", "机位", "上网", "价格", "营业")
SUPPORTING_TERMS = ("餐饮", "餐厅", "小吃", "娱乐", "酒吧", "KTV", "台球", "影院", "营业", "评分")
RENT_TERMS = ("出租", "招租", "租金", "月租", "商铺", "门面", "转让")


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
    return build_rule_search_queries(project, payload)


async def discover_urls_for_payload(
    project: SiteProjectRecord,
    payload: dict[str, Any],
    *,
    settings: CrawlerSettings,
    client: SearchDiscoveryClient,
    queries: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], str | None, list[dict[str, str]]]:
    if not settings.search_enabled:
        return [], [], [], "爬虫搜索发现未启用", [
            _search_error("system", "", "disabled", "爬虫搜索发现未启用")
        ]

    providers = _provider_list(settings.search_provider)
    queries = queries or build_search_queries(project, payload)
    relevant_results: list[tuple[int, SearchResult, dict[str, Any]]] = []
    considered_results: list[dict[str, Any]] = []
    errors: list[str] = []
    search_errors: list[dict[str, str]] = []
    seen: set[str] = set()
    filtered_count = 0

    for query in queries:
        for provider in providers:
            try:
                if hasattr(client, "discover_provider"):
                    from app.data_source.crawler.search_provider import provider_registry

                    registry = provider_registry(client)
                    if provider not in registry:
                        raise ValueError(f"不支持的搜索 Provider: {provider}")
                    results = await registry[provider].search(
                        query, max_results=max(1, settings.search_max_results),
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
                normalized_result = SearchResult(
                    url=normalized_url,
                    title=result.title,
                    snippet=result.snippet,
                    query=result.query or query,
                    provider=result.provider or provider,
                )
                score, reasons, eligible = score_search_result(project, payload, normalized_result)
                annotated = {
                    **normalized_result.model_dump(),
                    "relevance_score": score,
                    "relevance_reasons": reasons,
                    "eligible": eligible,
                }
                considered_results.append(annotated)
                if eligible:
                    relevant_results.append((score, normalized_result, annotated))
                else:
                    search_errors.append(
                        _search_error(
                            normalized_result.provider or provider,
                            normalized_result.query or query,
                            "irrelevant_result",
                            f"{normalized_url}（相关性 {score} 分）",
                        )
                    )
                if len(relevant_results) >= settings.search_max_results:
                    break
            if len(relevant_results) >= settings.search_max_results:
                break
        if len(relevant_results) >= settings.search_max_results:
            break

    relevant_results.sort(key=lambda item: item[0], reverse=True)
    selected_results = relevant_results[: settings.search_max_results]
    payloads = [
        {
            **payload,
            "city": project.city,
            "district": project.district,
            "project_address": project.address,
            "url": result.url,
            "discovered_by_search": True,
            "search_query": result.query,
            "search_result": annotated,
        }
        for _, result, annotated in selected_results
    ]
    if selected_results:
        return payloads, queries, considered_results, None, search_errors

    error_message = "；".join(errors)
    if considered_results:
        extra = f"搜索到 {len(considered_results)} 个候选网页，但均与目标名称、位置或业务类型不匹配"
        error_message = f"{error_message}；{extra}" if error_message else extra
    if filtered_count:
        extra = f"域名过滤后无可用结果，过滤 {filtered_count} 个"
        error_message = f"{error_message}；{extra}" if error_message else extra
    return payloads, queries, considered_results, error_message or "未发现可抓取的公开网页", search_errors


def score_search_result(
    project: SiteProjectRecord,
    payload: dict[str, Any],
    result: SearchResult,
) -> tuple[int, list[str], bool]:
    """对搜索结果做确定性相关性判断，防止把城市百科等泛页面写入业务数据。"""

    title_and_snippet = _normalize_match_text(f"{result.title or ''} {result.snippet or ''}")
    domain = (urlparse(result.url).netloc or "").lower()
    task_type = str(payload.get("task_type") or "")
    reasons: list[str] = []
    score = 0

    name_aliases = _name_aliases(str(payload.get("name") or ""))
    name_match = next((alias for alias in name_aliases if alias in title_and_snippet), None)
    if name_match:
        score += 70
        reasons.append(f"命中目标名称：{name_match}")

    location_aliases = _location_aliases(project, payload)
    location_match = next((alias for alias in location_aliases if alias in title_and_snippet), None)
    if location_match:
        score += 25
        reasons.append(f"命中位置：{location_match}")

    if task_type == "rent":
        business_match = next((term for term in RENT_TERMS if _normalize_match_text(term) in title_and_snippet), None)
        if business_match:
            score += 60
            reasons.append(f"命中租赁关键词：{business_match}")
        eligible = bool(business_match and location_match and score >= 70)
    else:
        terms = COMPETITOR_TERMS if task_type == "competitor" else SUPPORTING_TERMS
        business_match = next((term for term in terms if _normalize_match_text(term) in title_and_snippet), None)
        if business_match:
            score += 15
            reasons.append(f"命中业务关键词：{business_match}")
        eligible = bool(name_match and score >= 70)

    if any(domain == item or domain.endswith("." + item) for item in LOW_SIGNAL_DOMAINS):
        score = max(0, score - 40)
        reasons.append("泛内容域名降权")
        eligible = eligible and bool(name_match) and score >= 70

    if not eligible:
        reasons.append("未达到自动抓取相关性门槛")
    return score, reasons, eligible


def page_matches_target(payload: dict[str, Any], markdown: str) -> tuple[bool, list[str]]:
    """对自动搜索选中的实际页面再次校验；手动 URL 由用户明确指定，不做名称拦截。"""

    if not payload.get("discovered_by_search"):
        return True, ["用户或已有数据明确提供 URL"]

    content = _normalize_match_text(markdown[:12000])
    task_type = str(payload.get("task_type") or "")
    reasons: list[str] = []

    if task_type in {"competitor", "supporting"}:
        alias = next((item for item in _name_aliases(str(payload.get("name") or "")) if item in content), None)
        if not alias:
            return False, ["页面未出现目标商户名称"]
        reasons.append(f"页面命中目标名称：{alias}")
        return True, reasons

    if task_type == "rent":
        rent_term = next((term for term in RENT_TERMS if _normalize_match_text(term) in content), None)
        location = next(
            (
                item
                for item in _payload_location_aliases(payload)
                if item in content
            ),
            None,
        )
        if not rent_term:
            reasons.append("页面未出现出租、租金或商铺等租赁关键词")
        if not location:
            reasons.append("页面未出现项目地址或区县")
        return bool(rent_term and location), reasons or ["页面租赁信息与项目位置匹配"]

    return False, ["未知爬虫任务类型"]


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
        match = re.search(
            r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            flags=re.I | re.S,
        ) or re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
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


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").lower(), flags=re.UNICODE)


def _name_aliases(name: str) -> list[str]:
    raw_aliases = [
        name,
        re.sub(r"[（(].*?[）)]", "", name),
        re.sub(r"[（(].*?[）)]", "", name).removesuffix("店"),
    ]
    aliases: list[str] = []
    for value in raw_aliases:
        normalized = _normalize_match_text(value)
        if len(normalized) >= 3 and normalized not in aliases:
            aliases.append(normalized)
    return sorted(aliases, key=len, reverse=True)


def _location_aliases(project: SiteProjectRecord, payload: dict[str, Any]) -> list[str]:
    return _dedupe_match_aliases(
        [
            str(payload.get("address") or ""),
            project.address or "",
            project.district or "",
            (project.address or "").removesuffix("地铁站"),
            (project.district or "").removesuffix("区"),
        ]
    )


def _payload_location_aliases(payload: dict[str, Any]) -> list[str]:
    address = str(payload.get("address") or "")
    return _dedupe_match_aliases(
        [
            address,
            address.removesuffix("地铁站"),
            str(payload.get("project_address") or ""),
            str(payload.get("district") or ""),
            str(payload.get("district") or "").removesuffix("区"),
        ]
    )


def _dedupe_match_aliases(values: list[str]) -> list[str]:
    aliases: list[str] = []
    for value in values:
        normalized = _normalize_match_text(value)
        if len(normalized) >= 2 and normalized not in aliases:
            aliases.append(normalized)
    return sorted(aliases, key=len, reverse=True)


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
