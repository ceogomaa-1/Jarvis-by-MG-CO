"""Tiny in-memory ring buffer of recent backend errors, readable via a diagnostic
endpoint (/api/_chatdiag). Lets production failures be pinpointed without server-log
access. Best-effort, resets on restart, holds only an error type + short message."""
import time
from collections import deque

_RECENT: "deque[dict]" = deque(maxlen=25)


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
