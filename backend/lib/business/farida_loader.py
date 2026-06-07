"""
Pure-function loader for farida.md — no external dependencies.
Importable in tests without the supabase / httpx / anthropic stack.
"""

import os

FARIDA_USER_ID = "899a08aa-98d9-4bcc-96c6-f581940425e0"

_FARIDA_MD = os.path.join(os.path.dirname(__file__), "farida.md")


def user_id_to_uuid(user_id: str) -> str:
    """Normalise a user_<hex> or plain UUID string to canonical UUID form."""
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def is_farida(user_id: str) -> bool:
    return user_id_to_uuid(user_id) == FARIDA_USER_ID


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
    return _section(md_path, "Opening Message", "Knowledge Block")


def load_persona_block(md_path: str = _FARIDA_MD) -> str:
    """Return the knowledge + behavioral rules for system-prompt injection."""
    knowledge = _section(md_path, "Knowledge Block", "Behavioral Rules")
    rules = _section(md_path, "Behavioral Rules")
    if not knowledge and not rules:
        return ""
    parts = []
    if knowledge:
        parts.append(
            "## About Mohamed\n\n"
            "You know Mohamed Gomaa deeply and personally. "
            "Answer anything Farida asks about him using only the following truths — "
            "never fabricate details not listed here:\n\n" + knowledge
        )
    if rules:
        parts.append("## How to Behave in This Conversation\n\n" + rules)
    return "\n\n".join(parts)
