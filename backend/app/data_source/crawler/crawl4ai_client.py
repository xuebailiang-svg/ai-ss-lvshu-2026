from __future__ import annotations

import asyncio
from dataclasses import dataclass


class Crawl4AIUnavailableError(RuntimeError):
    pass


def ensure_crawl4ai_available() -> None:
    try:
        import crawl4ai  # noqa: F401
    except Exception as exc:
        raise Crawl4AIUnavailableError("请安装 crawl4ai 并执行 crawl4ai-setup") from exc


@dataclass(slots=True)
class CrawledPage:
    url: str
    markdown: str
    success: bool
    error_message: str | None = None


class Crawl4AIClient:
    async def crawl(self, url: str, *, timeout_seconds: int = 60) -> CrawledPage:
        ensure_crawl4ai_available()
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

        async def _run() -> CrawledPage:
            browser_config = BrowserConfig(headless=True, verbose=False)
            run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)
                markdown = getattr(result, "markdown", "") or ""
                if hasattr(markdown, "raw_markdown"):
                    markdown = markdown.raw_markdown
                return CrawledPage(
                    url=url,
                    markdown=str(markdown or ""),
                    success=bool(getattr(result, "success", True)),
                    error_message=getattr(result, "error_message", None),
                )

        return await asyncio.wait_for(_run(), timeout=timeout_seconds)
