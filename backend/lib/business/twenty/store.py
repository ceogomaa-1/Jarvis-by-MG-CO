"""
Persistence for the GHL -> Twenty migration: the structure map and the import map.

Backed by Supabase (PostgREST) using the service-role key, mirroring the access
pattern in connectors/registry.py. Two tables (see supabase/migrations/batch57_twenty_crm.sql):

  crm_structure_map   ghl pipeline/stage/field/tag id  <->  twenty id  (+ extra jsonb)
  crm_import_map      ghl record id  <->  twenty record id  (per record_type)

Both are keyed by user_id and have unique constraints so upserts are idempotent and
re-running the importer never duplicates.
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
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


# ── structure map ────────────────────────────────────────────────────────────
async def upsert_structure(user_id: str, ghl_kind: str, ghl_id: str, twenty_id: str, extra: dict | None = None) -> bool:
    if not _enabled() or not ghl_id or not twenty_id:
        return False
    payload = {
        "user_id": _user_id_to_uuid(user_id),
        "ghl_kind": ghl_kind,
        "ghl_id": ghl_id,
        "twenty_id": twenty_id,
        "extra": extra or {},
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/crm_structure_map?on_conflict=user_id,ghl_kind,ghl_id",
                headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                json=payload,
                timeout=10.0,
            )
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"TWENTY.store: upsert_structure failed: {e}")
        return False


async def load_structure_map(user_id: str) -> dict[tuple[str, str], dict]:
    """Return {(ghl_kind, ghl_id): {twenty_id, extra}} for the user."""
    if not _enabled():
        return {}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/crm_structure_map",
                headers=_headers(),
                params={
                    "select": "ghl_kind,ghl_id,twenty_id,extra",
                    "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return {
                (r["ghl_kind"], r["ghl_id"]): {"twenty_id": r["twenty_id"], "extra": r.get("extra") or {}}
                for r in resp.json()
            }
    except Exception as e:
        print(f"TWENTY.store: load_structure_map failed: {e}")
    return {}


# ── import map ───────────────────────────────────────────────────────────────
async def record_import(user_id: str, ghl_id: str, twenty_id: str, record_type: str) -> bool:
    if not _enabled() or not ghl_id or not twenty_id:
        return False
    payload = {
        "user_id": _user_id_to_uuid(user_id),
        "ghl_id": ghl_id,
        "twenty_id": twenty_id,
        "record_type": record_type,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/crm_import_map?on_conflict=user_id,ghl_id,record_type",
                headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
                json=payload,
                timeout=10.0,
            )
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"TWENTY.store: record_import failed: {e}")
        return False


async def load_import_map(user_id: str) -> dict[tuple[str, str], str]:
    """Return {(record_type, ghl_id): twenty_id} for fast idempotency lookups."""
    if not _enabled():
        return {}
    out: dict[tuple[str, str], str] = {}
    offset = 0
    try:
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/crm_import_map",
                    headers=_headers({"Range-Unit": "items", "Range": f"{offset}-{offset + 999}"}),
                    params={
                        "select": "ghl_id,twenty_id,record_type",
                        "user_id": f"eq.{_user_id_to_uuid(user_id)}",
                    },
                    timeout=15.0,
                )
                if resp.status_code not in (200, 206):
                    break
                rows = resp.json()
                for r in rows:
                    out[(r["record_type"], r["ghl_id"])] = r["twenty_id"]
                if len(rows) < 1000:
                    break
                offset += 1000
    except Exception as e:
        print(f"TWENTY.store: load_import_map failed: {e}")
    return out
