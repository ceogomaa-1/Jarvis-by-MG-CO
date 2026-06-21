"""
Naming helpers for Twenty metadata.

Twenty field `name` must be a camelCase identifier (letters/digits, starting with a
letter); option `value` must be an UPPER_SNAKE token. These helpers turn arbitrary
GHL labels into valid identifiers deterministically, so re-running the mirror with
the same GHL labels always produces the same Twenty names (idempotency).
"""
import re


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z0-9]+", text or "") if w]


def to_camel(label: str, *, fallback: str = "field") -> str:
    """'Lead Source #1' -> 'leadSource1'. Always returns a valid identifier."""
    words = _words(label)
    if not words:
        return fallback
    head = words[0].lower()
    rest = "".join(w[:1].upper() + w[1:].lower() for w in words[1:])
    name = head + rest
    # Identifiers can't start with a digit.
    if name[0].isdigit():
        name = f"{fallback}{name[0].upper()}{name[1:]}"
    return name


def to_option_value(label: str, *, fallback: str = "OPTION") -> str:
    """'In Progress' -> 'IN_PROGRESS'. Always returns a valid UPPER_SNAKE token."""
    words = _words(label)
    if not words:
        return fallback
    value = "_".join(w.upper() for w in words)
    if value[0].isdigit():
        value = f"_{value}"
    return value
