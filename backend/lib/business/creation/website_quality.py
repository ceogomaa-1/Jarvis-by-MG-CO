"""Shared identity and quality gates for Jarvis website artifacts.

The creation pipeline must never treat a chat transcript, a raw prompt, or a
generic emergency template as a finished client website.  These checks run
before preview, persistence, GitHub, or Vercel.
"""

from __future__ import annotations

import html as html_module
import re
from typing import Any


_URL_RE = re.compile(r"https?://[^\s<>()\"']+", re.IGNORECASE)
_QUOTED_CLIENT_RE = re.compile(
    r"(?:\b(?:this|for)\s+)?[\"“]([^\"”\n]{2,100})[\"”]"
    r"(?:\s+(?:client|business|company|restaurant|clinic|brand))?",
    re.IGNORECASE,
)
_SITE_FOR_RE = re.compile(
    r"\b(?:website|web\s*site|web\s*page|webpage|landing\s*page|site)\s+for\s+"
    r"(?:my\s+|our\s+|the\s+)?"
    r"([A-Z0-9][A-Za-z0-9&'’+.-]*(?:\s+[A-Z0-9][A-Za-z0-9&'’+.-]*){1,7})",
)
_PROMPT_WORD_RE = re.compile(r"[a-z0-9]+")
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_SCRIPT_STYLE_RE = re.compile(
    r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>",
    re.IGNORECASE | re.DOTALL,
)

_JARVIS_UI_MARKERS = (
    "ask jarvis",
    "jarvis knows you",
    "/business/chat",
    "live preview",
    "autonomous jarvis",
    "jarvis os1",
    "creation 1.0",
)


def extract_url(message: str) -> str:
    """Return the first explicit HTTP(S) URL in a build request."""
    match = _URL_RE.search(message or "")
    return match.group(0).rstrip(".,);]") if match else ""


def extract_client_name(message: str) -> str:
    """Best-effort extraction of an explicitly named target business.

    We deliberately stay conservative. A false positive is worse than leaving
    the model to infer the target from the full brief because this value becomes
    an identity assertion used by the quality gate.
    """
    text = (message or "").strip()
    if not text:
        return ""

    quoted = _QUOTED_CLIENT_RE.search(text)
    if quoted:
        candidate = quoted.group(1).strip(" \t-–—")
        if not _looks_like_instruction(candidate):
            return candidate[:100]

    named = _SITE_FOR_RE.search(text)
    if named:
        candidate = named.group(1).strip(" \t-–—")
        if not _looks_like_instruction(candidate):
            return candidate[:100]
    return ""


def should_use_owner_company(message: str, client_name: str = "") -> bool:
    """Whether the account owner's company is actually the requested site target."""
    if client_name:
        return False
    return bool(
        re.search(
            r"\b(?:my|our)\s+(?:company|business|brand|website|web\s*site|site)\b",
            message or "",
            re.IGNORECASE,
        )
    )


def normalise_url(value: Any) -> str:
    """Extract and normalize a URL from a CRM field value."""
    if isinstance(value, dict):
        for key in ("primaryLinkUrl", "url", "href", "value"):
            if value.get(key):
                return normalise_url(value[key])
        return ""
    if isinstance(value, list):
        for item in value:
            found = normalise_url(item)
            if found:
                return found
        return ""
    text = str(value or "").strip()
    if not text:
        return ""
    explicit = extract_url(text)
    if explicit:
        return explicit
    if re.match(r"^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/.*)?$", text, re.IGNORECASE):
        return f"https://{text}"
    return ""


def visible_text(document: str) -> str:
    """Collapse an HTML document to searchable visible text."""
    without_code = _SCRIPT_STYLE_RE.sub(" ", document or "")
    without_tags = _TAG_RE.sub(" ", without_code)
    return _normalise_text(html_module.unescape(without_tags))


def prompt_leaked(document: str, user_message: str) -> bool:
    """Detect long verbatim prompt fragments in a rendered artifact."""
    page_text = visible_text(document)
    words = _PROMPT_WORD_RE.findall((user_message or "").lower())
    if len(words) < 10:
        return False

    # Check several 10-word windows so a prefixed label or a clipped prompt is
    # still caught without flagging normal short phrases such as a company name.
    last_start = min(len(words) - 10, 30)
    for start in range(0, last_start + 1, 5):
        probe = " ".join(words[start : start + 10])
        if len(probe) >= 45 and probe in page_text:
            return True
    return False


def validate_standalone_html(
    document: str,
    user_message: str = "",
    context: dict | None = None,
) -> list[str]:
    """Return human-readable blockers for a standalone HTML artifact."""
    context = context or {}
    errors: list[str] = []
    raw = (document or "").strip()
    low = raw.lower()
    text = visible_text(raw)

    if not raw:
        return ["HTML is empty"]
    if not low.startswith("<!doctype html"):
        errors.append("missing <!DOCTYPE html>")
    for closing in ("</head>", "</body>", "</html>"):
        if closing not in low:
            errors.append(f"missing {closing}")
    if "<meta name=\"viewport\"" not in low and "<meta name='viewport'" not in low:
        errors.append("missing responsive viewport metadata")
    if len(raw) < 8_000:
        errors.append("page is too small to be the requested high-craft complete site")
    if len(re.findall(r"<section\b", low)) < 5:
        errors.append("page has fewer than five substantive sections")
    if "<nav" not in low:
        errors.append("missing site navigation")
    if not re.search(r"<(?:a|button)\b", low):
        errors.append("missing a call-to-action control")
    if "prefers-reduced-motion" not in low:
        errors.append("missing reduced-motion accessibility handling")
    if "lorem ipsum" in low or "[placeholder" in low or "todo" in low:
        errors.append("contains placeholder content")
    if prompt_leaked(raw, user_message):
        errors.append("contains a verbatim fragment of the user's instruction")

    marker = next((item for item in _JARVIS_UI_MARKERS if item in text), None)
    if marker:
        errors.append(f"contains Jarvis/chat UI content ({marker})")

    client_name = (context.get("client_name") or extract_client_name(user_message)).strip()
    owner_company = (context.get("company_name") or "").strip()
    if client_name and _normalise_text(client_name) not in text:
        errors.append(f"does not visibly identify the target business '{client_name}'")
    if (
        client_name
        and owner_company
        and _normalise_text(client_name) != _normalise_text(owner_company)
        and _normalise_text(owner_company) in text
    ):
        errors.append("uses the account owner's company as the client brand")

    return _dedupe(errors)


def validate_site_payload(
    payload: dict,
    user_message: str = "",
    context: dict | None = None,
) -> list[str]:
    """Validate the creative fields returned by the Next.js site model."""
    context = context or {}
    errors: list[str] = []
    page = (payload.get("page_tsx") or "").strip()
    layout = (payload.get("layout_tsx") or "").strip()
    css = (payload.get("globals_css") or "").strip()
    needs_db = bool(payload.get("needs_database"))

    if not page:
        errors.append("app/page.tsx is empty")
    elif not re.match(r"^[\"']use client[\"'];?", page):
        errors.append("app/page.tsx does not begin with a use-client directive")
    if len(page) < 5_000:
        errors.append("app/page.tsx is too small for the requested complete site")
    if page.lower().count("<section") < 5:
        errors.append("app/page.tsx has fewer than five substantive sections")
    if "```" in page or "```" in layout or "```" in css:
        errors.append("generated files contain markdown fences")
    if re.search(r"\b(?:todo|rest of|implementation here|lorem ipsum)\b", page, re.IGNORECASE):
        errors.append("app/page.tsx contains truncated or placeholder content")
    if not layout or "globals.css" not in layout:
        errors.append("app/layout.tsx is missing or does not import globals.css")
    if "@tailwind base" not in css or "--bg" not in css or "--accent" not in css:
        errors.append("app/globals.css is missing Tailwind directives or design tokens")
    if "framer-motion" in page:
        errors.append("uses retired framer-motion import instead of motion/react")
    if prompt_leaked(page, user_message):
        errors.append("app/page.tsx contains a verbatim fragment of the user's instruction")

    page_text = _normalise_text(page)
    marker = next((item for item in _JARVIS_UI_MARKERS if item in page_text), None)
    if marker:
        errors.append(f"app/page.tsx contains Jarvis/chat UI content ({marker})")

    client_name = (context.get("client_name") or extract_client_name(user_message)).strip()
    owner_company = (context.get("company_name") or "").strip()
    if client_name and _normalise_text(client_name) not in page_text:
        errors.append(f"app/page.tsx does not identify target business '{client_name}'")
    if (
        client_name
        and owner_company
        and _normalise_text(client_name) != _normalise_text(owner_company)
        and _normalise_text(owner_company) in page_text
    ):
        errors.append("app/page.tsx uses the account owner's company as the client brand")

    allowed_imports = {
        "react",
        "motion/react",
        "gsap",
        "gsap/ScrollTrigger",
        "lucide-react",
        "@/lib/utils",
        "@/components/contact-form",
        "@/lib/supabase",
    }
    for module in re.findall(r"\bfrom\s+[\"']([^\"']+)[\"']", page):
        if module not in allowed_imports:
            errors.append(f"app/page.tsx imports unsupported module '{module}'")

    if needs_db and not (payload.get("contact_form_tsx") or "").strip():
        errors.append("database-enabled site is missing components/contact-form.tsx")
    return _dedupe(errors)


def validate_deployable_site(site: dict, user_message: str = "") -> list[str]:
    """Final mutation boundary before GitHub/Vercel receives a generated project."""
    files = site.get("files") or []
    by_path = {
        str(item.get("path") or ""): str(item.get("content") or "")
        for item in files
        if isinstance(item, dict)
    }
    required = ("package.json", "app/layout.tsx", "app/globals.css", "app/page.tsx")
    errors = [f"missing required file {path}" for path in required if not by_path.get(path)]
    if errors:
        return errors

    payload = {
        "page_tsx": by_path["app/page.tsx"],
        "layout_tsx": by_path["app/layout.tsx"],
        "globals_css": by_path["app/globals.css"],
        "needs_database": bool(site.get("needs_database")),
        "contact_form_tsx": by_path.get("components/contact-form.tsx", ""),
    }
    errors.extend(validate_site_payload(payload, user_message))
    return _dedupe(errors)


def _looks_like_instruction(candidate: str) -> bool:
    low = _normalise_text(candidate)
    return (
        len(low) < 2
        or low.startswith(("build ", "create ", "design ", "analyze ", "analyse "))
        or low in {"website", "landing page", "client", "business", "company"}
    )


def _normalise_text(value: str) -> str:
    return " ".join(_PROMPT_WORD_RE.findall((value or "").lower()))


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
