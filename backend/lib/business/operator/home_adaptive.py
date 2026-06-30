"""
Phase 3 — adaptive Home intelligence (Batch 67).

Once telemetry (business_home_usage) accumulates, a nightly job detects the user's
real engagement pattern and PROPOSES a reorg. It never auto-applies: it writes a
pending row to business_home_suggestions with a one-click Apply/Undo on the frontend.
Adaptation is the message, not silent customization.

The pattern is explainable: rank blocks by how often the user acts on them first /
clicks through, build a proposed order, and only suggest when (a) there's enough signal
and (b) the proposal meaningfully differs from what they have now.
"""
import os
from collections import Counter

import httpx

from backend.lib.business import home_layout as hl

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

MIN_EVENTS = 12          # don't propose anything until we've actually watched the user
MIN_DISTINCT_BLOCKS = 3  # need a real ordering, not one block clicked repeatedly


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


async def _get(client: httpx.AsyncClient, table: str, params: dict) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        resp = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_read_headers(),
                                params=params, timeout=10.0)
        if resp.status_code == 200 and isinstance(resp.json(), list):
            return resp.json()
    except Exception as e:
        print(f"HOME_ADAPTIVE: read {table} failed: {e}")
    return []


def rank_engagement(events: list[dict]) -> list[str]:
    """Weighted block ranking from telemetry: first-actions and click-throughs count most."""
    weights = {"first_action": 3.0, "click_through": 2.0, "view": 0.5, "dwell": 0.0}
    score: Counter = Counter()
    for e in events:
        key = e.get("block_key")
        if not key or key not in hl.BLOCK_KEYS:
            continue
        score[key] += weights.get(e.get("event_type", ""), 0.0)
        # Dwell adds a small amount proportional to attention.
        if e.get("event_type") == "dwell" and e.get("dwell_ms"):
            score[key] += min(2.0, (e["dwell_ms"] or 0) / 15000.0)
    return [k for k, _ in score.most_common()]


def propose_order(engaged: list[str]) -> list[str]:
    """Engaged blocks first (by rank), then the rest in canonical order."""
    order = [k for k in engaged if k in hl.BLOCK_KEYS]
    for k in hl.DEFAULT_ORDER:
        if k not in order:
            order.append(k)
    return order


def _meaningfully_different(proposed: list[str], current: list[str], top_n: int = 4) -> bool:
    """True if the top of the proposed order differs from the current top."""
    return proposed[:top_n] != current[:top_n]


def build_suggestion_message(engaged: list[str]) -> str:
    titles = {k: k.replace("_", " ").title() for k in hl.BLOCK_KEYS}
    flow = " → ".join(titles.get(k, k) for k in engaged[:3])
    return (f"I noticed you keep going straight to {flow}. "
            f"Want me to reorganize Home around how you actually work?")


async def detect_and_suggest(user_id: str) -> dict:
    """Compute one user's pattern and, if warranted, write a pending suggestion."""
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "suggested": False}
    async with httpx.AsyncClient() as client:
        # Skip if a suggestion is already pending — never stack proposals.
        pending = await _get(client, "business_home_suggestions", {
            "select": "id", "user_id": f"eq.{user_id}", "status": "eq.pending", "limit": "1"})
        if pending:
            return {"ok": True, "suggested": False, "reason": "already_pending"}

        events = await _get(client, "business_home_usage", {
            "select": "block_key,event_type,dwell_ms,position",
            "user_id": f"eq.{user_id}",
            "event_type": "in.(first_action,click_through,view,dwell)",
            "order": "created_at.desc", "limit": "300"})
        actionable = [e for e in events if e.get("event_type") in ("first_action", "click_through")]
        if len(actionable) < MIN_EVENTS:
            return {"ok": True, "suggested": False, "reason": "insufficient_signal"}

        engaged = rank_engagement(events)
        if len(engaged) < MIN_DISTINCT_BLOCKS:
            return {"ok": True, "suggested": False, "reason": "not_enough_distinct"}

        layout_row = await _get(client, "business_home_layout", {
            "select": "layout,is_default", "user_id": f"eq.{user_id}", "limit": "1"})
        current = hl.normalize_layout((layout_row[0] if layout_row else {}).get("layout"))
        proposed_order = propose_order(engaged)
        if not _meaningfully_different(proposed_order, current["order"]):
            return {"ok": True, "suggested": False, "reason": "already_aligned"}

        sizes = current.get("sizes") or {k: dict(hl.DEFAULT_SIZES[k]) for k in hl.BLOCK_KEYS}
        proposed_layout = {
            "version": 1, "order": proposed_order, "sizes": sizes,
            "hidden": current.get("hidden", []),
            "layouts": hl.build_grid_layouts(proposed_order, sizes, current.get("hidden", [])),
        }
        message = build_suggestion_message(engaged)
        try:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_home_suggestions",
                headers={**_read_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
                json={
                    "user_id": user_id, "message": message,
                    "proposed_layout": proposed_layout,
                    "evidence": {"pattern": engaged[:5], "sample_size": len(actionable)},
                    "status": "pending",
                }, timeout=10.0)
            ok = resp.status_code in (200, 201, 204)
        except Exception as e:
            print(f"HOME_ADAPTIVE: write suggestion failed: {e}")
            ok = False
    return {"ok": ok, "suggested": ok, "pattern": engaged[:3]}
