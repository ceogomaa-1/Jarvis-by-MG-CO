"""
Brand config CRUD. One row per user with logo, banner, accent color, display name,
North Star target, and Operator Agent settings.
"""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {
        **_read_headers(),
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


_DEFAULTS = {
    "logo_url": None,
    "banner_url": None,
    "accent_color": "#c84b31",
    "display_name": None,
    "north_star_target_usd": 1000000,
    "north_star_target_label": "$1M ARR",
    "operator_enabled": False,
    "operator_daily_budget_usd": 5.00,
}


async def get_brand_config(user_id: str) -> dict:
    """Returns the user's brand config, falling back to defaults for missing fields."""
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"user_id": user_id, **_DEFAULTS}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_brand_config",
                headers=_read_headers(),
                params={"select": "*", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            rows = resp.json()
            if rows:
                return {**_DEFAULTS, **rows[0]}
    except Exception as e:
        print(f"BRAND: get_brand_config exception: {e}")
    return {"user_id": user_id, **_DEFAULTS}


async def upsert_brand_config(user_id: str, fields: dict) -> dict | None:
    """Upsert allowed fields. Returns merged row or None on failure."""
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return None

    allowed = {
        "logo_url", "banner_url", "accent_color", "display_name",
        "north_star_target_usd", "north_star_target_label",
        "operator_enabled", "operator_daily_budget_usd",
    }
    payload = {k: v for k, v in fields.items() if k in allowed}
    if not payload:
        return await get_brand_config(user_id)
    payload["user_id"] = user_id
    payload["updated_at"] = "now()"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_brand_config",
                headers=_write_headers(),
                json=payload,
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            row = data[0] if isinstance(data, list) and data else data
            return {**_DEFAULTS, **row}
        print(f"BRAND: upsert failed {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"BRAND: upsert exception: {e}")
    return None


async def list_operator_enabled_users() -> list[dict]:
    """Returns users where operator_enabled = true. Used by the operator cron."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_brand_config",
                headers=_read_headers(),
                params={
                    "select": "user_id,operator_daily_budget_usd,north_star_target_usd,north_star_target_label,display_name",
                    "operator_enabled": "eq.true",
                },
                timeout=15.0,
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"BRAND: list_operator_enabled_users exception: {e}")
    return []
