from __future__ import annotations

import asyncio
from dataclasses import dataclass


class Crawl4AIUnavailableError(RuntimeError):
    pass


class PlaywrightRuntimeUnavailableError(RuntimeError):
    pass


def ensure_crawl4ai_available() -> None:
    try:
        import crawl4ai  # noqa: F401
    except Exception as exc:
        raise Crawl4AIUnavailableError("独立爬虫运行时缺少 crawl4ai，请重新执行 scripts/crawler/install.sh") from exc


def ensure_playwright_chromium_available() -> None:
    """Verify that Playwright and its Chromium browser are actually runnable.

    crawl4ai can be importable while Playwright's browser binary is missing.
    In that case the data-source status should report a real failure instead
    of showing the crawler as usable.
    """

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise PlaywrightRuntimeUnavailableError("独立爬虫运行时缺少 Playwright，请重新执行 scripts/crawler/install.sh") from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            raise PlaywrightRuntimeUnavailableError(
                "Playwright Chromium 未安装，请重新执行 scripts/crawler/install.sh"
            ) from exc
        raise PlaywrightRuntimeUnavailableError(f"Playwright Chromium 启动失败：{message}") from exc


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
