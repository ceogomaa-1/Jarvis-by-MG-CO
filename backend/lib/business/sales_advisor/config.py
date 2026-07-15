"""Sales Advisor — env gating + the tunable caps (research breadth, report size).

The feature needs only the Anthropic key to run (research degrades gracefully:
no Maps key → skip the Places profile; no Brave key → web_search falls back to
DuckDuckGo). Kill-switch: SALES_ADVISOR_ENABLED=false.
"""
import os

from backend.lib.business.model_router import OPUS


def enabled() -> bool:
    """True iff Sales Advisor should be exposed (nav item + chat tools)."""
    if os.getenv("SALES_ADVISOR_ENABLED", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def model() -> str:
    """Pitch generation runs on the smart tier by default — a closer deck is exactly
    the 'strategic / pitch deck' class model_router routes to Opus. Env-overridable."""
    return os.getenv("SALES_ADVISOR_MODEL", "").strip() or OPUS


# ── Research caps (cost + latency guards) ────────────────────────────────────────
MAX_SITE_PAGES = int(os.getenv("SALES_ADVISOR_SITE_PAGES", "4") or "4")     # homepage + subpages
MAX_SEARCHES = int(os.getenv("SALES_ADVISOR_SEARCHES", "3") or "3")         # Brave/DDG queries
MAX_RESEARCH_CHARS = int(os.getenv("SALES_ADVISOR_RESEARCH_CHARS", "26000") or "26000")
REPORT_MAX_TOKENS = int(os.getenv("SALES_ADVISOR_MAX_TOKENS", "12000") or "12000")  # live runs hit ~7.8k
PLACES_TIMEOUT = 20.0
