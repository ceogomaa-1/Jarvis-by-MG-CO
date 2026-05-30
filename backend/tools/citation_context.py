from contextvars import ContextVar
from urllib.parse import urlparse

sources_collector: ContextVar[list | None] = ContextVar('sources_collector', default=None)


def init_collector() -> list:
    """Initialize a per-request source list. Call at start of each chat turn."""
    sources = []
    sources_collector.set(sources)
    return sources


def _favicon_for(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return f"https://www.google.com/s2/favicons?domain={host}&sz=64"
    except Exception:
        return ""


def _hostname(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "")
    except Exception:
        return ""


def add_source(url: str, title: str = "", snippet: str = "", source_type: str = "web") -> int:
    """Add a source. Returns 1-indexed position. Dedups by URL."""
    coll = sources_collector.get()
    if coll is None:
        return 0
    for i, s in enumerate(coll, 1):
        if s["url"] == url:
            return i
    coll.append({
        "url": url,
        "title": title or url,
        "snippet": snippet[:300] if snippet else "",
        "type": source_type,
        "favicon": _favicon_for(url),
        "domain": _hostname(url),
    })
    return len(coll)


def get_sources() -> list:
    coll = sources_collector.get()
    if not coll:
        return []
    return [{**s, "index": i + 1} for i, s in enumerate(coll)]
