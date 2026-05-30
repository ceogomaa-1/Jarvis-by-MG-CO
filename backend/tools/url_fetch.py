import re
import httpx
import trafilatura

from backend.tools.registry import register_tool
from backend.tools.citation_context import add_source

FETCH_TIMEOUT = 5.0
MAX_CONTENT_CHARS = 20000
USER_AGENT = "Mozilla/5.0 (compatible; JarvisBot/1.0; +https://jarvis-by-mg-co.vercel.app)"

URL_REGEX = re.compile(r'https?://[^\s<>"\'`)\]]+', re.IGNORECASE)


def extract_urls(text: str, limit: int = 5) -> list[str]:
    """Extract HTTP(S) URLs from text. Dedup, strip trailing punctuation, cap at limit."""
    if not isinstance(text, str):
        return []
    found = URL_REGEX.findall(text)
    seen = set()
    out = []
    for u in found:
        u = u.rstrip('.,;:!?')
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out


async def fetch_url_content(url: str) -> dict:
    """Fetch a URL and return {url, title, content, error}. Errors return error string, empty content."""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url)
        if resp.status_code >= 400:
            return {"url": url, "title": "", "content": "", "error": f"HTTP {resp.status_code}"}
        ctype = resp.headers.get("content-type", "").lower()
        if "html" not in ctype and "text" not in ctype:
            return {"url": url, "title": "", "content": "", "error": f"unsupported content-type: {ctype}"}
        html = resp.text
    except httpx.TimeoutException:
        return {"url": url, "title": "", "content": "", "error": "timeout (5s)"}
    except Exception as e:
        return {"url": url, "title": "", "content": "", "error": f"fetch failed: {type(e).__name__}"}

    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        include_images=False,
        output_format="txt",
        favor_precision=True,
    )
    if not extracted or len(extracted.strip()) < 50:
        return {"url": url, "title": "", "content": "", "error": "could not extract main content"}

    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip()[:200] if title_match else url

    if len(extracted) > MAX_CONTENT_CHARS:
        extracted = extracted[:MAX_CONTENT_CHARS] + "\n\n[content truncated]"

    return {"url": url, "title": title, "content": extracted, "error": None}


@register_tool(
    name="fetch_url",
    description="Fetch and read the full content of a web page. Use this when you have a specific URL (from web_search results, or one the user mentioned) and need to read its full content to give detailed feedback, summarize it, or answer specific questions about it. Do not use for URLs the user just pasted — those are already fetched and provided in your context.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch (must start with http:// or https://)",
            }
        },
        "required": ["url"],
    },
)
async def fetch_url_tool(url: str) -> str:
    print(f"FETCH_URL: url={url!r}")
    result = await fetch_url_content(url)
    if result["error"]:
        return f"Could not fetch {url}: {result['error']}"
    idx = add_source(
        url=result["url"],
        title=result["title"],
        snippet=result["content"][:200],
        source_type="fetched",
    )
    return (
        f"[Source {idx}] {result['title']}\n"
        f"URL: {result['url']}\n\n"
        f"{result['content']}"
    )
