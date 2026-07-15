"""Supabase-backed persistence for Sales Advisor reports (service-role, PostgREST/httpx).

Mirrors leads/store.py exactly: service key, RLS-on-no-policies table, no end-user access.
Table: mgco_sales_reports — one row per analysis job. The row doubles as the job record
(status/progress live on it) so the cockpit can poll a single endpoint.
"""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_TABLE = "mgco_sales_reports"

# Columns the cockpit list view needs — no jsonb payloads (they can be hundreds of KB).
_LIST_COLS = "id,business_name,maps_url,status,progress,error,model,created_at,updated_at"


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = (user_id or "").removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _headers(extra: dict | None = None) -> dict:
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


async def create_report(user_id: str, *, business_name: str, maps_url: str | None,
                        notes: str | None, model: str) -> str | None:
    if not enabled():
        return None
    payload = {"user_id": _user_id_to_uuid(user_id), "business_name": business_name,
               "maps_url": maps_url, "notes": notes, "status": "running",
               "progress": "Locating the business profile…", "model": model}
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.post(f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                                headers=_headers({"Prefer": "return=representation"}),
                                json=payload, timeout=10.0)
        if resp.status_code in (200, 201):
            data = resp.json()
            return (data[0] if isinstance(data, list) else data).get("id")
        print(f"SALES.store: create_report failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"SALES.store: create_report failed: {e}")
    return None


async def update_report(report_id: str, fields: dict) -> bool:
    if not enabled() or not report_id or not fields:
        return False
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                                 headers=_headers({"Prefer": "return=minimal"}),
                                 params={"id": f"eq.{report_id}"},
                                 json={**fields, "updated_at": "now()"}, timeout=15.0)
        if resp.status_code in (200, 204):
            return True
        print(f"SALES.store: update_report failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"SALES.store: update_report failed: {e}")
    return False


async def get_report(user_id: str, report_id: str) -> dict | None:
    if not enabled() or not report_id:
        return None
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/{_TABLE}", headers=_headers(),
                               params={"select": "*",
                                       "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                       "id": f"eq.{report_id}", "limit": "1"}, timeout=15.0)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"SALES.store: get_report failed: {e}")
    return None


async def latest_report(user_id: str) -> dict | None:
    if not enabled():
        return None
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/{_TABLE}", headers=_headers(),
                               params={"select": "*",
                                       "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                       "order": "created_at.desc", "limit": "1"}, timeout=15.0)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"SALES.store: latest_report failed: {e}")
    return None


async def list_reports(user_id: str, limit: int = 50) -> list[dict]:
    if not enabled():
        return []
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/{_TABLE}", headers=_headers(),
                               params={"select": _LIST_COLS,
                                       "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                       "order": "created_at.desc", "limit": str(limit)}, timeout=15.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"SALES.store: list_reports failed: {e}")
    return []


async def delete_report(user_id: str, report_id: str) -> bool:
    if not enabled() or not report_id:
        return False
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(f"{SUPABASE_URL}/rest/v1/{_TABLE}",
                                  headers=_headers({"Prefer": "return=minimal"}),
                                  params={"user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                          "id": f"eq.{report_id}"}, timeout=10.0)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"SALES.store: delete_report failed: {e}")
        return False
