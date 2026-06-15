"""Shared web-research helpers for the Real Estate Operator Suite — robots.txt-aware
Playwright page fetching, reused by seller_research and contact_enrichment."""
import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

MAX_PAGES = 5
PAGE_TIMEOUT_MS = 10_000
USER_AGENT = "Mozilla/5.0 (compatible; JarvisOS1Bot/1.0)"


def allowed_by_robots(url: str) -> bool:
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


async def fetch_pages(urls: list[str], max_pages: int = MAX_PAGES) -> tuple[list[tuple[str, str]], bool]:
    """Returns (list of (url, page_text), playwright_used)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return [], False

    pages: list[tuple[str, str]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            for url in urls[:max_pages]:
                if not await asyncio.to_thread(allowed_by_robots, url):
                    continue
                try:
                    page = await browser.new_page(user_agent=USER_AGENT)
                    await page.goto(url, timeout=PAGE_TIMEOUT_MS)
                    text = await page.inner_text("body")
                    pages.append((url, text[:5000]))
                    await page.close()
                except Exception as e:
                    print(f"WEB_RESEARCH: page fetch failed for {url}: {e}")
            await browser.close()
        return pages, True
    except Exception as e:
        print(f"WEB_RESEARCH: Playwright unavailable at runtime: {e}")
        return [], False
