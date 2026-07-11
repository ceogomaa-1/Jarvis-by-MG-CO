"""Shared web-research helpers for the Real Estate Operator Suite.

Fast, honest page fetching reused by seller_research and contact_enrichment:
  1. STATIC-FIRST  — try httpx + trafilatura (backend.tools.url_fetch) first; it's
     ~5s and handles most contact pages without launching a browser.
  2. CONCURRENT    — all candidate URLs fetched in parallel (capped semaphore),
     so N slow sites cost ~max(one) instead of N×timeout.
  3. JS FALLBACK   — only the pages that came back thin/failed get a Playwright
     pass (single reused browser, wait_until="domcontentloaded", short timeout).
  4. HARD BUDGET   — the whole step is wrapped in an overall time budget; when it
     elapses we stop and return whatever was gathered. Research NEVER runs minutes.
  5. ROBOTS        — time-boxed and fail-open so it can't add serial latency.

An optional `progress_cb(message: str)` async callback lets callers stream
human-readable progress ("Checking 6 sources…", "2 unreachable, read 3…").
"""
import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from backend.tools.url_fetch import fetch_url_content

# Widened candidate cap — safe now that fetching is concurrent + budgeted, so we
# "try harder" (more sources) without being slower.
MAX_PAGES = 8
FETCH_CONCURRENCY = 5          # parallel fetches in flight at once
PAGE_TIMEOUT_MS = 7_000        # Playwright per-page goto timeout (light wait)
ROBOTS_TIMEOUT_S = 3.0         # cap on a single robots.txt read
OVERALL_BUDGET_S = 35.0        # hard ceiling on the whole research-fetch step
MIN_STATIC_CHARS = 300         # below this, a page is "thin" → try JS fallback
USER_AGENT = "Mozilla/5.0 (compatible; RueOS1Bot/1.0)"


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


async def _allowed_by_robots_async(url: str) -> bool:
    """Time-boxed, fail-open robots check — never lets robots.txt block research."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(allowed_by_robots, url), timeout=ROBOTS_TIMEOUT_S
        )
    except Exception:
        return True


def _progress_summary(found: int, unreachable: int, pending: int) -> str:
    parts: list[str] = []
    if found:
        parts.append(f"read {found} source{'s' if found != 1 else ''}")
    if unreachable:
        parts.append(f"{unreachable} unreachable")
    if pending:
        parts.append(f"checking {pending} more")
    return (", ".join(parts) + "…") if parts else "Still searching…"


async def _emit(progress_cb, message: str) -> None:
    if not progress_cb:
        return
    try:
        await progress_cb(message)
    except Exception:
        pass


async def _playwright_pass(urls: list[str]) -> dict[str, str] | None:
    """JS fallback for thin/failed pages. One reused browser + context, concurrent,
    light wait. Returns {url: text} or None if Playwright isn't available.
    These URLs already cleared the robots check during the static pass."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    results: dict[str, str] = {}
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context(user_agent=USER_AGENT)

            async def one(url: str) -> None:
                async with sem:
                    page = None
                    try:
                        page = await context.new_page()
                        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                        text = await page.inner_text("body")
                        if text and text.strip():
                            results[url] = text[:5000]
                    except Exception as e:
                        print(f"WEB_RESEARCH: JS fetch failed for {url}: {e}")
                    finally:
                        if page is not None:
                            try:
                                await page.close()
                            except Exception:
                                pass

            await asyncio.gather(*(one(u) for u in urls), return_exceptions=True)
            await context.close()
            await browser.close()
        return results
    except Exception as e:
        print(f"WEB_RESEARCH: Playwright unavailable at runtime: {e}")
        return None


async def fetch_pages(
    urls: list[str], max_pages: int = MAX_PAGES, progress_cb=None
) -> tuple[list[tuple[str, str]], bool]:
    """Returns (list of (url, page_text), playwright_used).

    Static-first + concurrent + JS-fallback, all under a hard overall time budget.
    On budget exhaustion, returns whatever was gathered so far (never hangs)."""
    urls = list(dict.fromkeys(u for u in urls if u))[:max_pages]
    if not urls:
        return [], False

    loop = asyncio.get_event_loop()
    deadline = loop.time() + OVERALL_BUDGET_S
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    collected: dict[str, str] = {}
    needs_js: list[str] = []
    unreachable = 0

    await _emit(progress_cb, f"Checking {len(urls)} source{'s' if len(urls) != 1 else ''}…")

    # ── Static-first pass (concurrent) ─────────────────────────────────────────
    async def static_one(url: str) -> None:
        nonlocal unreachable
        async with sem:
            if not await _allowed_by_robots_async(url):
                return
            try:
                res = await fetch_url_content(url)
            except Exception:
                res = {"error": "exception", "content": ""}
            content = (res.get("content") or "").strip()
            if not res.get("error") and len(content) >= MIN_STATIC_CHARS:
                collected[url] = content[:5000]
            else:
                needs_js.append(url)
                if res.get("error"):
                    unreachable += 1

    static_tasks = [asyncio.create_task(static_one(u)) for u in urls]
    try:
        await asyncio.wait_for(
            asyncio.gather(*static_tasks, return_exceptions=True),
            timeout=max(0.1, deadline - loop.time()),
        )
    except asyncio.TimeoutError:
        for t in static_tasks:
            t.cancel()

    await _emit(progress_cb, _progress_summary(len(collected), unreachable, len(needs_js)))

    # ── JS fallback for thin/failed pages, within remaining budget ─────────────
    used_playwright = False
    remaining = deadline - loop.time()
    if needs_js and remaining > 5.0:
        try:
            pw_pages = await asyncio.wait_for(_playwright_pass(needs_js), timeout=remaining)
            if pw_pages is not None:
                used_playwright = True
                for url, text in pw_pages.items():
                    if text and url not in collected:
                        collected[url] = text
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            print(f"WEB_RESEARCH: JS fallback pass failed: {e}")

    pages = [(u, collected[u]) for u in urls if u in collected]
    return pages, used_playwright
