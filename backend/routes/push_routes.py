"""
Batch 50.1 — Web Push subscription management for Rue Notes reminders.

Persists browser PushManager subscriptions into the existing
`public.push_subscriptions` table (user_id, endpoint, p256dh, auth),
upserting on (user_id, endpoint) so re-subscribing (e.g. after a key
rotation) doesn't create duplicate rows. backend/cron/notes_reminders.py
reads from this table to deliver "push" reminders via pywebpush.
"""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agent import _SUPABASE_KEY, _SUPABASE_URL, _notes_headers

router = APIRouter()


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


def _require_supabase():
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise HTTPException(503, "Notes storage is not configured")


@router.post("/push/subscribe/{user_id}")
async def subscribe(user_id: str, body: PushSubscribeRequest):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_SUPABASE_URL}/rest/v1/push_subscriptions",
            headers={
                **_notes_headers("return=representation"),
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            params={"on_conflict": "user_id,endpoint"},
            json={
                "user_id": user_id,
                "endpoint": body.endpoint,
                "p256dh": body.keys.p256dh,
                "auth": body.keys.auth,
            },
            timeout=10.0,
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(500, f"Failed to save push subscription: {resp.text[:200]}")
    return {"subscribed": True}


@router.post("/push/unsubscribe/{user_id}")
async def unsubscribe(user_id: str, body: PushUnsubscribeRequest):
    _require_supabase()
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{_SUPABASE_URL}/rest/v1/push_subscriptions",
            headers=_notes_headers("return=minimal"),
            params={"user_id": f"eq.{user_id}", "endpoint": f"eq.{body.endpoint}"},
            timeout=10.0,
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(500, f"Failed to remove push subscription: {resp.text[:200]}")
    return {"subscribed": False}
