"""General-purpose URL scraper for the Rue OS1 business chat agent.

Entry point: scrape(url, max_pages=1) -> {url, title, text, links, source_type, error}

- Renders JS-heavy pages (Wix, Squarespace, etc.) with headless Playwright/Chromium.
- Falls back to a stealth static fetch (curl_cffi browser impersonation — the same
  engine Scrapling's Fetcher uses — with Scrapling's parser as a text-extraction
  fallback) for sites whose bot walls block a plain httpx UA.
- Falls back to httpx + trafilatura for static pages or if neither is available.
- Extracts text from linked PDFs (e.g. restaurant menu PDFs) with pypdf.
- When max_pages > 1, auto-discovers and fetches obvious sub-pages (menu, about,
  contact, location, hours, and linked PDFs) from the same domain and merges
  their text — useful for building a full client profile from a homepage URL.

Never hard-fails: every helper returns a result dict with an `error` field
instead of raising, so a bad URL degrades to a clear message.
"""
import asyncio
import html
import re
from io import BytesIO
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from pypdf import PdfReader

from backend.lib.business.connectors.base import ConnectorResult
from backend.tools.citation_context import add_source
from backend.tools.url_fetch import fetch_url_content
from backend.tools.web_search import web_search

USER_AGENT = "Mozilla/5.0 (compatible; JarvisOS1Bot/1.0; +https://jarvis-by-mg-co.vercel.app)"
HTTPX_TIMEOUT = 5.0
PLAYWRIGHT_TIMEOUT_MS = 15_000
MAX_CONTENT_CHARS = 20000
MAX_LINKS = 40
MAX_PAGES = 5

SUBPAGE_KEYWORDS = ["menu", "hours", "contact", "about", "location", "order",
                    "service", "pricing", "book", "team"]

LINK_REGEX = re.compile(r'href=["\']([^"\'#]+)', re.IGNORECASE)
TITLE_REGEX = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _extract_title(html_text: str, fallback: str) -> str:
    m = TITLE_REGEX.search(html_text)
    if not m:
        return fallback
    return html.unescape(m.group(1)).strip()[:200] or fallback


def _extract_links(html_text: str, base_url: str) -> list[str]:
    seen: set[str] = set()
    links: list[str] = []
    for href in LINK_REGEX.findall(html_text):
        href = html.unescape(href).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href).split("#")[0]
        if urlparse(full).scheme not in ("http", "https"):
            continue
        if full not in seen:
            seen.add(full)
            links.append(full)
        if len(links) >= MAX_LINKS:
            break
    return links


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_CONTENT_CHARS:
        return text[:MAX_CONTENT_CHARS] + "\n\n[content truncated]"
    return text


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(parts)


async def _fetch_pdf(url: str) -> dict:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=HTTPX_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "pdf", "error": f"timeout ({HTTPX_TIMEOUT}s)"}
    except Exception as e:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "pdf", "error": f"fetch failed: {type(e).__name__}"}

    if resp.status_code >= 400:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "pdf", "error": f"HTTP {resp.status_code}"}

    try:
        text = await asyncio.to_thread(_extract_pdf_text, resp.content)
    except Exception as e:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "pdf", "error": f"PDF parse failed: {type(e).__name__}"}

    if not text.strip():
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "pdf", "error": "could not extract text from PDF"}

    title = url.rsplit("/", 1)[-1]
    return {"url": url, "title": title, "text": _truncate(text), "links": [], "source_type": "pdf", "error": None}


async def _fetch_httpx(url: str) -> dict:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=HTTPX_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            resp = await client.get(url)
    except httpx.TimeoutException:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "static", "error": f"timeout ({HTTPX_TIMEOUT}s)"}
    except Exception as e:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "static", "error": f"fetch failed: {type(e).__name__}"}

    final_url = str(resp.url)
    if resp.status_code >= 400:
        return {"url": final_url, "title": "", "text": "", "links": [], "source_type": "static", "error": f"HTTP {resp.status_code}"}

    ctype = resp.headers.get("content-type", "").lower()
    if "application/pdf" in ctype or _is_pdf_url(final_url):
        return await _fetch_pdf(final_url)

    if "html" not in ctype and "text" not in ctype:
        return {"url": final_url, "title": "", "text": "", "links": [], "source_type": "static", "error": f"unsupported content-type: {ctype}"}

    html_text = resp.text
    links = _extract_links(html_text, final_url)
    title = _extract_title(html_text, final_url)

    extracted = trafilatura.extract(
        html_text,
        include_comments=False,
        include_tables=True,
        include_images=False,
        output_format="txt",
        favor_precision=True,
    )
    if not extracted or len(extracted.strip()) < 50:
        return {"url": final_url, "title": title, "text": "", "links": links, "source_type": "static", "error": "could not extract main content"}

    return {"url": final_url, "title": title, "text": _truncate(extracted), "links": links, "source_type": "static", "error": None}


def _extract_main_text(html_text: str) -> str:
    """trafilatura first; Scrapling's parser as fallback for pages trafilatura rejects."""
    extracted = trafilatura.extract(
        html_text,
        include_comments=False,
        include_tables=True,
        include_images=False,
        output_format="txt",
        favor_precision=True,
    )
    if extracted and len(extracted.strip()) >= 50:
        return extracted
    try:  # Scrapling (base install) — adaptive parser, no browser deps
        from scrapling.parser import Selector
        text = Selector(html_text).get_all_text(ignore_tags=("script", "style"))
        return text if text and len(text.strip()) >= 50 else ""
    except Exception:
        return ""


async def _fetch_stealth(url: str) -> dict:
    """Static fetch with real-browser TLS/header impersonation via curl_cffi (the engine
    behind Scrapling's Fetcher). Gets past bot walls that 403 the plain httpx UA. Optional
    dependency — returns a soft error (→ httpx fallback) if not installed."""
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "stealth", "error": "curl_cffi not available at runtime"}

    try:
        async with AsyncSession() as s:
            resp = await s.get(url, impersonate="chrome", timeout=int(HTTPX_TIMEOUT) + 5,
                               allow_redirects=True)
    except Exception as e:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "stealth", "error": f"fetch failed: {type(e).__name__}"}

    final_url = str(resp.url)
    if resp.status_code >= 400:
        return {"url": final_url, "title": "", "text": "", "links": [], "source_type": "stealth", "error": f"HTTP {resp.status_code}"}

    ctype = (resp.headers.get("content-type") or "").lower()
    if "application/pdf" in ctype or _is_pdf_url(final_url):
        return await _fetch_pdf(final_url)
    if "html" not in ctype and "text" not in ctype:
        return {"url": final_url, "title": "", "text": "", "links": [], "source_type": "stealth", "error": f"unsupported content-type: {ctype}"}

    html_text = resp.text
    links = _extract_links(html_text, final_url)
    title = _extract_title(html_text, final_url)
    extracted = _extract_main_text(html_text)
    if not extracted:
        return {"url": final_url, "title": title, "text": "", "links": links, "source_type": "stealth", "error": "could not extract main content"}
    return {"url": final_url, "title": title, "text": _truncate(extracted), "links": links, "source_type": "stealth", "error": None}


async def _fetch_playwright(url: str) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "rendered", "error": "Playwright not available at runtime"}

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page(user_agent=USER_AGENT)
                resp = await page.goto(url, timeout=PLAYWRIGHT_TIMEOUT_MS, wait_until="domcontentloaded")
                if resp and resp.status >= 400:
                    return {"url": url, "title": "", "text": "", "links": [], "source_type": "rendered", "error": f"HTTP {resp.status}"}
                content_html = await page.content()
                text = (await page.inner_text("body")).strip()
                title = (await page.title()) or url
                final_url = page.url
                links = _extract_links(content_html, final_url)
            finally:
                await browser.close()
    except Exception as e:
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "rendered", "error": f"Playwright failed: {type(e).__name__}"}

    if not text:
        return {"url": final_url, "title": title, "text": "", "links": links, "source_type": "rendered", "error": "empty page content"}

    return {"url": final_url, "title": title, "text": _truncate(text), "links": links, "source_type": "rendered", "error": None}


async def _fetch_one_page(url: str) -> dict:
    """Fetch a single URL. Renders JS with Playwright, falls back to the stealth
    impersonated fetch (curl_cffi/Scrapling), then to the plain httpx fetch."""
    if _is_pdf_url(url):
        return await _fetch_pdf(url)

    rendered = await _fetch_playwright(url)
    if rendered["text"]:
        return rendered

    stealth = await _fetch_stealth(url)
    if stealth["text"]:
        return stealth

    static = await _fetch_httpx(url)
    if static["text"]:
        return static

    # All failed — the httpx error tends to be more specific (HTTP status etc.)
    return static if static["error"] else (stealth if stealth["error"] else rendered)


def _select_subpages(links: list[str], base_url: str, limit: int) -> list[str]:
    """Pick up to `limit` same-domain sub-page links: PDFs first, then known keywords."""
    if limit <= 0:
        return []
    base_domain = urlparse(base_url).netloc
    base_path = base_url.rstrip("/")

    pdf_links: list[str] = []
    keyword_links: list[str] = []
    for link in links:
        if urlparse(link).netloc != base_domain or link.rstrip("/") == base_path:
            continue
        lower = link.lower()
        if lower.endswith(".pdf"):
            pdf_links.append(link)
        elif any(kw in lower for kw in SUBPAGE_KEYWORDS):
            keyword_links.append(link)

    ordered: list[str] = []
    seen: set[str] = set()
    for link in pdf_links + keyword_links:
        if link in seen:
            continue
        seen.add(link)
        ordered.append(link)
        if len(ordered) >= limit:
            break
    return ordered


async def scrape(url: str, max_pages: int = 1) -> dict:
    """Fetch `url` and, if max_pages > 1, related sub-pages (menu/about/contact/etc.
    and linked PDFs) from the same domain. Returns:
        {url, title, text, links, source_type, error}
    `error` is None on success (even if some sub-pages individually failed).
    """
    if not url or not re.match(r"^https?://", url, re.IGNORECASE):
        return {"url": url, "title": "", "text": "", "links": [], "source_type": "error", "error": "Invalid URL — must start with http:// or https://"}

    max_pages = max(1, min(int(max_pages or 1), MAX_PAGES))

    main = await _fetch_one_page(url)
    if main["error"]:
        return {
            "url": main["url"],
            "title": main.get("title", ""),
            "text": "",
            "links": main.get("links", []),
            "source_type": main["source_type"],
            "error": main["error"],
        }

    pages = [main]
    if max_pages > 1:
        subpages = _select_subpages(main["links"], main["url"], max_pages - 1)
        if subpages:
            results = await asyncio.gather(*(_fetch_one_page(u) for u in subpages))
            pages.extend(r for r in results if r["text"])

    all_links: list[str] = []
    seen: set[str] = set()
    for p in pages:
        for link in p.get("links", []):
            if link not in seen:
                seen.add(link)
                all_links.append(link)

    return {
        "url": main["url"],
        "title": main.get("title") or url,
        "text": "\n\n".join(f"=== {p['url']} ===\n{p['text']}" for p in pages),
        "links": all_links,
        "source_type": main["source_type"],
        "error": None,
    }


async def execute_web_tool(action_name: str, inp: dict) -> ConnectorResult:
    """Dispatch for the always-on `web__*` tool family (no connector required)."""
    if action_name == "search":
        query = (inp.get("query") or "").strip()
        if not query:
            return ConnectorResult(ok=False, error="`query` is required")
        # web_search returns a numbered, citation-registered results block (it calls
        # add_source internally so [1], [2] line up with the request's source list).
        text = await web_search(query)
        return ConnectorResult(ok=True, data={"query": query, "results": text})

    if action_name == "fetch_url":
        url = (inp.get("url") or "").strip()
        if not url:
            return ConnectorResult(ok=False, error="`url` is required")
        result = await fetch_url_content(url)
        if result.get("error"):
            return ConnectorResult(ok=False, error=f"Could not fetch {url}: {result['error']}")
        idx = add_source(
            url=result["url"],
            title=result["title"],
            snippet=result["content"][:200],
            source_type="fetched",
        )
        return ConnectorResult(ok=True, data={
            "source_index": idx,
            "url": result["url"],
            "title": result["title"],
            "content": result["content"],
        })

    if action_name == "scrape_website":
        url = (inp.get("url") or "").strip()
        if not url:
            return ConnectorResult(ok=False, error="`url` is required")
        max_pages = inp.get("max_pages", 1)
        result = await scrape(url, max_pages=max_pages)
        if result["error"]:
            return ConnectorResult(ok=False, error=f"Could not fetch {result['url']}: {result['error']}")
        return ConnectorResult(ok=True, data=result)
    return ConnectorResult(ok=False, error=f"Unknown web tool: {action_name}")
