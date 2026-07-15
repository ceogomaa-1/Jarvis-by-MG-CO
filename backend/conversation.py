"""
Conversation history persistence via Supabase.

Required Supabase table — run once in the SQL editor:

    CREATE TABLE conversations (
        id          BIGSERIAL PRIMARY KEY,
        user_id     TEXT        NOT NULL,
        role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
        content     TEXT        NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX conversations_user_id_created_at
        ON conversations (user_id, created_at DESC);
"""

import os
from datetime import datetime, timezone

import httpx

_SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_TABLE = "conversations"


def _headers(prefer: str = "return=minimal") -> dict:
    return {
        "apikey": _SUPABASE_KEY,
        "Authorization": f"Bearer {_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


async def save_conversation_turn(user_id: str, role: str, content: str, attachments: list[dict] | None = None) -> bool:
    """Insert a single message into the conversations table immediately."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return False
    try:
        payload = {"user_id": user_id, "role": role, "content": content}
        if attachments:
            payload["attachments"] = attachments
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                headers=_headers(),
                json=payload,
                timeout=10.0,
            )
        if resp.status_code not in (200, 201):
            print(f"CONV: save failed ({resp.status_code}): {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"CONV: save_conversation_turn error: {e}")
        return False


async def get_minutes_since_last_turn(user_id: str) -> int | None:
    """Minutes elapsed since the most recent saved message, or None if no history.

    Grounds Rue's sense of elapsed time — without it the model only sees a
    timestamp-free transcript and treats hours-old messages as seconds-old.
    """
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                headers=_headers("return=representation"),
                params={
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc",
                    "limit": 1,
                    "select": "created_at",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            return None
        rows = resp.json()
        if not rows or not rows[0].get("created_at"):
            return None
        last = datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, int((now - last).total_seconds() / 60))
    except Exception as e:
        print(f"CONV: get_minutes_since_last_turn error: {e}")
        return None


async def get_conversation_history(user_id: str, limit: int = 20) -> list[dict]:
    """Return the last `limit` messages for this user, oldest first."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                headers=_headers("return=representation"),
                params={
                    "user_id": f"eq.{user_id}",
                    "order": "created_at.desc",
                    "limit": limit,
                    "select": "role,content,attachments,created_at",
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                # Schema drift (e.g. `attachments` column missing in this
                # environment) shouldn't hide a user's entire history —
                # fall back to the columns that have always existed.
                print(f"CONV: get failed ({resp.status_code}): {resp.text[:200]} — retrying without attachments")
                resp = await client.get(
                    f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                    headers=_headers("return=representation"),
                    params={
                        "user_id": f"eq.{user_id}",
                        "order": "created_at.desc",
                        "limit": limit,
                        "select": "role,content,created_at",
                    },
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    print(f"CONV: get failed ({resp.status_code}): {resp.text[:200]}")
                    return []
                rows = resp.json()
                for row in rows:
                    row.setdefault("attachments", [])
                return list(reversed(rows)) if rows else []
        rows = resp.json()
        # Fetched newest-first; reverse so oldest is first for chat context
        return list(reversed(rows)) if rows else []
    except Exception as e:
        print(f"CONV: get_conversation_history error: {e}")
        return []


def get_minutes_since_history(history: list[dict]) -> int | None:
    """Derive the latest-message gap from an already-fetched history snapshot."""
    if not history:
        return None
    raw = history[-1].get("created_at")
    if not raw:
        return None
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - last).total_seconds() / 60))
    except (TypeError, ValueError):
        return None
