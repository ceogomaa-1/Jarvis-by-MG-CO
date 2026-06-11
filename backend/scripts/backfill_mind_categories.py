"""
One-time backfill for Batch 47 (The Mind): embed, categorize, and build
similarity edges for every existing business_user_memories row that doesn't
have an embedding yet.

Run manually once:
    python -m backend.scripts.backfill_mind_categories
"""
import asyncio

import httpx

from backend.utils.env import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from backend.lib.business.mind.ingest import process_new_memory

SUPABASE_KEY = SUPABASE_SERVICE_ROLE_KEY

BATCH_SIZE = 200
DELAY_SECONDS = 0.3


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


async def _fetch_unembedded_batch(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/business_user_memories",
        headers=_read_headers(),
        params={
            "select": "id,user_id,memory",
            "embedding": "is.null",
            "order": "created_at.asc",
            "limit": str(BATCH_SIZE),
        },
        timeout=30.0,
    )
    return resp.json() if resp.status_code == 200 else []


async def run_backfill() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("BACKFILL: Supabase not configured")
        return

    processed = 0
    async with httpx.AsyncClient() as client:
        while True:
            rows = await _fetch_unembedded_batch(client)
            if not rows:
                break
            for row in rows:
                memory_id = row.get("id")
                user_id = row.get("user_id")
                memory_text = row.get("memory") or ""
                if not memory_id or not user_id:
                    continue
                await process_new_memory(user_id, memory_id, memory_text)
                processed += 1
                print(f"BACKFILL: processed {processed} ({memory_id})")
                await asyncio.sleep(DELAY_SECONDS)

    print(f"BACKFILL: done — {processed} memories processed")


if __name__ == "__main__":
    asyncio.run(run_backfill())
