"""
Relationship Playbook ("the Bible") — Rue Personal relationship & dating
intelligence layer. Personal product only; never imported from business code.

Detects when the current turn is about dating, a partner/ex/crush, texting
someone the user is into, flirting, or a relationship conflict — and if so,
returns a system-prompt injection that switches Rue into the bible's
voice (and ethics/calibration guardrails) for that reply.
"""

import os
import re

import httpx

from backend.utils.env import ANTHROPIC_API_KEY

_BIBLE_MD = os.path.join(os.path.dirname(__file__), "relationship_bible.md")

_bible_cache: str | None = None


def load_bible(md_path: str = _BIBLE_MD) -> str:
    """Return the full bible markdown, cached after first read. Empty string on error."""
    global _bible_cache
    if md_path == _BIBLE_MD and _bible_cache is not None:
        return _bible_cache
    try:
        with open(md_path, encoding="utf-8") as fh:
            text = fh.read().strip()
    except Exception:
        text = ""
    if md_path == _BIBLE_MD:
        _bible_cache = text
    return text


def build_relationship_injection(md_path: str = _BIBLE_MD) -> str:
    """Return the full system-prompt injection for an active relationship turn.

    Empty string if the bible file is missing — callers should treat that as
    "no injection, behave normally."
    """
    bible = load_bible(md_path)
    if not bible:
        return ""
    return (
        "RELATIONSHIP MODE — ACTIVE FOR THIS REPLY:\n"
        "The user is talking about dating, a relationship, a partner, a crush, an ex, "
        "a text, or a fight. For this reply, adopt the voice and frameworks in the "
        "playbook below (sections 1-9) instead of your normal register — take a clear "
        "stance, name the user's blind spot, give an exact move and exact words. Avoid "
        "every phrase listed as a banned 'generic AI' tell in section 2.\n\n"
        "Section 7 (ethics) and section 8 (calibration) ALWAYS override this persona: "
        "if there's real grief, abuse, self-harm, a safety concern, or anyone underage "
        "involved, drop the swagger entirely and respond as a warm, careful, responsible "
        "presence instead — the persona never outranks the user's wellbeing.\n\n"
        + bible
    )


# ─── Relationship-context detection ────────────────────────────────────────

# Unambiguous on their own — a single hit is enough to trigger the bible.
_STRONG_TERMS = [
    "girlfriend", "boyfriend", "gf", "bf", "crush", "situationship",
    "fiance", "fiancee", "fiancée", "fiancé", "wife", "husband",
    "ex girlfriend", "ex-girlfriend", "ex boyfriend", "ex-boyfriend",
    "ex wife", "ex-wife", "ex husband", "ex-husband",
    "breakup", "break-up", "break up", "broke up", "breaking up",
    "ghosted", "ghosting", "no contact", "dtr",
    "what are we", "get her back", "get him back", "get them back",
    "win her back", "win him back", "mixed signals",
    "one night stand", "one-night stand",
    "left me on read", "left on read", "double text", "triple text",
]

# Ambiguous alone (could be about work, a calendar date, a sibling, etc.) —
# need a second signal, or get confirmed by the cheap Haiku classifier below.
_WEAK_TERMS = [
    "partner", "dating", "flirt", "flirting", "flirty", "jealous", "jealousy",
    "kiss", "kissed", "kissing", "marriage", "married", "wedding", "engaged",
    "propose", "proposal", "long distance", "ldr", "soulmate", "romantic",
    "she texted", "he texted", "texted her", "texted him",
    "she said", "he said", "she left", "he left", "left me",
    "to reply", "to text back", "haha yeah", "lol yeah",
    "had a fight", "got into a fight", "in a fight",
    "wants space", "want space", "needs space", "need space",
]

# "ex" as its own word — "my ex did X" matches; "ex-employer" / "example" do not
# (the lookahead excludes "ex-" compounds, and \b already excludes "example").
_EX_RE = re.compile(r"\bex\b(?!-)", re.IGNORECASE)


def _keyword_signal(text: str) -> tuple[bool, int]:
    """Return (strong_hit, weak_hit_count) for the lowercased combined text."""
    strong = any(term in text for term in _STRONG_TERMS) or bool(_EX_RE.search(text))
    weak_hits = sum(1 for term in _WEAK_TERMS if term in text)
    return strong, weak_hits


async def _confirm_with_haiku(message: str, recent_text: str = "") -> bool:
    """Cheap fallback classifier for ambiguous single-weak-term messages."""
    if not ANTHROPIC_API_KEY:
        return False
    prompt = (
        "Is this chat message part of a conversation about the user's dating life, "
        "a romantic partner, an ex, a crush, flirting, or a relationship conflict — "
        "as opposed to a business partner, a coworker, a calendar date, or an "
        "unrelated topic? Answer with exactly one word: yes or no.\n\n"
        f"Recent context: {recent_text[-500:]}\n"
        f"Message: {message}"
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 5,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if resp.status_code == 200:
            text = resp.json().get("content", [{}])[0].get("text", "").strip().lower()
            return text.startswith("y")
    except Exception:
        pass
    return False


async def is_relationship_context(message: str, recent_text: str = "") -> bool:
    """True if this turn should get the relationship-bible persona.

    Strong keyword/phrase hits trust immediately. Two or more weak hits
    together are treated as strong. A single weak hit is ambiguous (e.g.
    "partner", "date") and gets a yes/no check from Haiku.
    """
    if not message:
        return False

    combined = f"{recent_text} {message}".lower()
    strong, weak_hits = _keyword_signal(combined)

    if strong:
        return True
    if weak_hits >= 2:
        return True
    if weak_hits == 1:
        return await _confirm_with_haiku(message, recent_text)
    return False
