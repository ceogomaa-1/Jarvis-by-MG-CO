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


async def save_conversation_turn(user_id: str, role: str, content: str) -> bool:
    """Insert a single message into the conversations table immediately."""
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_SUPABASE_URL}/rest/v1/{_TABLE}",
                headers=_headers(),
                json={"user_id": user_id, "role": role, "content": content},
                timeout=10.0,
            )
        if resp.status_code not in (200, 201):
            print(f"CONV: save failed ({resp.status_code}): {resp.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"CONV: save_conversation_turn error: {e}")
        return False


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
                    "select": "role,content",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            print(f"CONV: get failed ({resp.status_code}): {resp.text[:200]}")
            return []
        rows = resp.json()
        # Fetched newest-first; reverse so oldest is first for chat context
        return list(reversed(rows)) if rows else []
    except Exception as e:
        print(f"CONV: get_conversation_history error: {e}")
        return []
