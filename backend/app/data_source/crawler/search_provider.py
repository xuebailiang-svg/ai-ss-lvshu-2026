from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.data_source.crawler.search_discovery import SearchDiscoveryClient, SearchResult


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, *, max_results: int, timeout_seconds: int) -> list[SearchResult]: ...


@dataclass
class HtmlSearchProvider:
    name: str
    client: SearchDiscoveryClient

    async def search(self, query: str, *, max_results: int, timeout_seconds: int) -> list[SearchResult]:
        return await self.client.discover_provider(
            self.name,
            query,
            max_results=max_results,
            timeout_seconds=timeout_seconds,
        )


def provider_registry(client: SearchDiscoveryClient | None = None) -> dict[str, SearchProvider]:
    search_client = client or SearchDiscoveryClient()
    return {
        name: HtmlSearchProvider(name=name, client=search_client)
        for name in ("duckduckgo_html", "bing_html")
    }
