"""Tiny in-memory ring buffer of recent backend errors, readable via a diagnostic
endpoint (/api/_chatdiag). Lets production failures be pinpointed without server-log
access. Best-effort, resets on restart, holds only an error type + short message."""
import time
from collections import deque

_RECENT: "deque[dict]" = deque(maxlen=25)
_USAGE: "deque[dict]" = deque(maxlen=25)


def record_error(where: str, name: str, err: BaseException) -> None:
    try:
        _RECENT.append({
            "ts": round(time.time(), 1),
            "where": where,
            "name": name,
            "error_type": type(err).__name__,
            "error": str(err)[:400],
        })
    except Exception:
        pass


def recent_errors() -> list:
    return list(_RECENT)


def record_usage(where: str, usage: dict) -> None:
    """Record privacy-safe model usage; never accepts prompts or user IDs."""
    try:
        _USAGE.append({
            "ts": round(time.time(), 1),
            "where": where,
            "model": str(usage.get("model", ""))[:80],
            "rounds": int(usage.get("rounds", 0) or 0),
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "cache_creation_input_tokens": int(usage.get("cache_creation_input_tokens", 0) or 0),
            "cache_read_input_tokens": int(usage.get("cache_read_input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
            "total_usd": float(usage.get("total_usd", 0) or 0),
        })
    except Exception:
        pass


def recent_usage() -> list:
    return list(_USAGE)
