"""
Pure-function loader for backend/farida.md (Jarvis Personal).
Zero external dependencies — importable in tests without the anthropic/supabase stack.
"""

import os

FARIDA_USER_ID = "899a08aa-98d9-4bcc-96c6-f581940425e0"

_FARIDA_MD = os.path.join(os.path.dirname(__file__), "farida.md")


def _is_farida(user_id: str) -> bool:
    """Return True iff user_id (any form) refers to Farida's account."""
    if not user_id:
        return False
    uid = user_id.strip().lower().removeprefix("user_")
    target = FARIDA_USER_ID.replace("-", "")
    return uid == FARIDA_USER_ID or uid.replace("-", "") == target


def _section(md_path: str, start_header: str, end_header: str | None = None) -> str:
    """Extract a ## section from a markdown file. Returns '' on any error."""
    try:
        with open(md_path, encoding="utf-8") as fh:
            text = fh.read()
        needle = f"\n## {start_header}"
        idx = text.find(needle)
        if idx == -1:
            return ""
        body_start = text.find("\n", idx + 1) + 1
        if end_header:
            end_needle = f"\n## {end_header}"
            end_idx = text.find(end_needle, body_start)
            return text[body_start:end_idx].strip() if end_idx != -1 else text[body_start:].strip()
        return text[body_start:].strip()
    except Exception:
        return ""


def load_greeting(md_path: str = _FARIDA_MD) -> str:
    """Return the Opening Message section verbatim."""
    return _section(md_path, "Opening Message", "Knowledge Block")


def load_persona_block(md_path: str = _FARIDA_MD) -> str:
    """Return knowledge + behavioral rules formatted for system-prompt injection."""
    knowledge = _section(md_path, "Knowledge Block", "Behavioral Rules")
    rules = _section(md_path, "Behavioral Rules")
    if not knowledge and not rules:
        return ""
    parts = []
    if knowledge:
        parts.append(
            "## About Mohamed\n\n"
            "You know Mohamed Gomaa deeply and personally. "
            "Answer anything this person asks about him using only the following truths — "
            "never fabricate details not listed here:\n\n" + knowledge
        )
    if rules:
        parts.append("## How to Behave in This Conversation\n\n" + rules)
    return "\n\n".join(parts)
