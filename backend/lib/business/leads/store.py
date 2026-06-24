"""Supabase-backed persistence for mgcoleads (service-role, via PostgREST/httpx).

Mirrors twenty/workspaces.py exactly: service key, RLS-protected tables, no end-user access.
Tables: mgco_lead_runs (one per search) + mgco_leads (scored businesses). Dedupe is by
(user_id, place_id) so re-running a query re-scores in place instead of duplicating.
"""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


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


# ── runs ─────────────────────────────────────────────────────────────────────────
async def find_recent_run(user_id: str, query: str, within_hours: int) -> dict | None:
    """Most recent run for this user+query inside the cache window, or None (cost control)."""
    if not enabled():
        return None
    from datetime import datetime, timedelta, timezone
    since = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                f"{SUPABASE_URL}/rest/v1/mgco_lead_runs",
                headers=_headers(),
                params={"select": "id,query,result_count,created_at",
                        "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                        "query": f"eq.{query}", "created_at": f"gte.{since}",
                        "order": "created_at.desc", "limit": "1"},
                timeout=10.0)
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"LEADS.store: find_recent_run failed: {e}")
    return None


async def create_run(user_id: str, *, query: str, industry: str | None, location: str | None,
                     provider: str, result_count: int, api_calls: int) -> str | None:
    if not enabled():
        return None
    payload = {"user_id": _user_id_to_uuid(user_id), "query": query, "industry": industry,
               "location": location, "provider": provider, "result_count": result_count,
               "api_calls": api_calls}
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.post(f"{SUPABASE_URL}/rest/v1/mgco_lead_runs",
                                headers=_headers({"Prefer": "return=representation"}),
                                json=payload, timeout=10.0)
        if resp.status_code in (200, 201):
            data = resp.json()
            return (data[0] if isinstance(data, list) else data).get("id")
    except Exception as e:
        print(f"LEADS.store: create_run failed: {e}")
    return None


# ── leads ────────────────────────────────────────────────────────────────────────
async def existing_by_place(user_id: str, place_ids: list[str]) -> dict[str, str]:
    """Map place_id → existing lead row id, for the given user (dedupe lookup)."""
    ids = [p for p in place_ids if p]
    if not enabled() or not ids:
        return {}
    quoted = ",".join(f'"{p}"' for p in ids)
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/mgco_leads",
                               headers=_headers(),
                               params={"select": "id,place_id",
                                       "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                       "place_id": f"in.({quoted})"},
                               timeout=10.0)
        if resp.status_code == 200:
            return {r["place_id"]: r["id"] for r in resp.json() if r.get("place_id")}
    except Exception as e:
        print(f"LEADS.store: existing_by_place failed: {e}")
    return {}


async def insert_leads(rows: list[dict]) -> int:
    if not enabled() or not rows:
        return 0
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.post(f"{SUPABASE_URL}/rest/v1/mgco_leads",
                                headers=_headers({"Prefer": "return=minimal"}),
                                json=rows, timeout=20.0)
        if resp.status_code in (200, 201, 204):
            return len(rows)
        print(f"LEADS.store: insert_leads failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"LEADS.store: insert_leads failed: {e}")
    return 0


async def update_lead(lead_id: str, fields: dict) -> bool:
    if not enabled() or not lead_id or not fields:
        return False
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(f"{SUPABASE_URL}/rest/v1/mgco_leads",
                                 headers=_headers({"Prefer": "return=minimal"}),
                                 params={"id": f"eq.{lead_id}"},
                                 json={**fields, "updated_at": "now()"}, timeout=10.0)
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"LEADS.store: update_lead failed: {e}")
        return False


async def list_leads(user_id: str, *, tier: str | None = None, limit: int = 50,
                     pushed: bool | None = None) -> list[dict]:
    if not enabled():
        return []
    params = {"select": "id,place_id,name,category,address,lat,lng,phone,website,rating,review_count,"
                        "price_level,score,tier,why,pitch,pushed_to_crm,crm_company_id",
              "user_id": f"eq.{_user_id_to_uuid(user_id)}",
              "order": "score.desc", "limit": str(limit)}
    if tier:
        params["tier"] = f"eq.{tier.upper()}"
    if pushed is not None:
        params["pushed_to_crm"] = f"eq.{str(pushed).lower()}"
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/mgco_leads", headers=_headers(),
                               params=params, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"LEADS.store: list_leads failed: {e}")
    return []


async def list_leads_for_run(user_id: str, run_id: str, limit: int = 50) -> list[dict]:
    """Leads from one cached run (so a cache hit returns that query's results, not all)."""
    if not enabled() or not run_id:
        return []
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/mgco_leads", headers=_headers(),
                               params={"select": "id,place_id,name,category,address,lat,lng,phone,website,"
                                                 "rating,review_count,price_level,score,tier,why,pitch,pushed_to_crm",
                                       "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                       "run_id": f"eq.{run_id}",
                                       "order": "score.desc", "limit": str(limit)}, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"LEADS.store: list_leads_for_run failed: {e}")
    return []


async def get_leads_by_ids(user_id: str, lead_ids: list[str]) -> list[dict]:
    if not enabled() or not lead_ids:
        return []
    quoted = ",".join(f'"{i}"' for i in lead_ids)
    try:
        async with httpx.AsyncClient() as c:
            resp = await c.get(f"{SUPABASE_URL}/rest/v1/mgco_leads", headers=_headers(),
                               params={"select": "id,name,category,address,phone,website,rating,"
                                                 "review_count,score,tier,why,pitch,pushed_to_crm",
                                       "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                                       "id": f"in.({quoted})"}, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"LEADS.store: get_leads_by_ids failed: {e}")
    return []
