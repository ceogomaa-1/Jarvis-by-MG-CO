"""Deterministic tool gate for Personal Rue.

Companion conversations should never enter an agent loop merely because tools
exist. Tools are offered only when the user explicitly asks for a live lookup
or an external action. This keeps emotional/supportive turns to one model call
and prevents accidental multi-round spend.
"""
from __future__ import annotations

import re


_EXPLICIT_TOOL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        # Notes, reminders, and tasks.
        r"\b(save|add|create|write|edit|update|delete|remove|mark|snooze|list|show|get|read)\b.{0,60}\b(note|notes|task|tasks|reminder|reminders)\b",
        r"\b(note|notes|task|tasks|reminder|reminders)\b.{0,40}\b(save|add|create|edit|update|delete|remove|mark|snooze|list|show)\b",
        # Time and date lookups.
        r"\b(what(?:'s| is)?|tell me|check|show me)\b.{0,24}\b(time|date|day of (?:the )?week)\b",
        # Calendar reads and writes.
        r"\b(what(?:'s| is)?|show|check|list|read)\b.{0,50}\b(calendar|schedule|appointments?|meetings?|events?)\b",
        r"\b(add|create|book|schedule|reschedule|move|cancel|delete)\b.{0,60}\b(calendar|appointments?|meetings?|events?)\b",
        # Email reads and sends.
        r"\b(show|check|read|search|find|list|send|write|draft|reply|forward)\b.{0,60}\b(email|emails|mail|inbox|gmail)\b",
        r"\b(email|emails|mail|inbox|gmail)\b.{0,40}\b(show|check|read|search|find|list|send|write|draft|reply|forward)\b",
        # Timers.
        r"\b(set|start|create)\b.{0,24}\btimer\b",
        # Explicit web/current-information requests.
        r"\b(search (?:the )?web|search online|look (?:it |this )?up|browse (?:the )?web|google (?:it|this))\b",
        r"\b(latest|current|today(?:'s)?)\b.{0,50}\b(news|weather|forecast|price|score|stock|exchange rate)\b",
        r"\b(weather|forecast)\b.{0,30}\b(today|tomorrow|this week|in\s+[A-Za-z])\b",
        # Search the user's connected documents/files.
        r"\b(search|find|look for|look up)\b.{0,50}\b(my|uploaded|connected)\b.{0,24}\b(documents?|files?|pdfs?)\b",
    )
)


def should_offer_personal_tools(message: str) -> bool:
    """Return True only for an explicit Personal tool/action request."""
    if not isinstance(message, str) or not message.strip():
        return False
    text = message.strip()
    return any(pattern.search(text) for pattern in _EXPLICIT_TOOL_PATTERNS)
