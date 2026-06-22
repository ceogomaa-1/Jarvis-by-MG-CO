"""One-time backfill: provision a Jarvis CRM workspace for every existing business user.

New signups get a workspace automatically via the onboarding hook
(`/business/onboard/complete` → `auto_provision_workspace`). Users who onboarded BEFORE
that hook existed have no workspace, so their CRM button never appears. This backfills them.

It reuses the SAME working flow the onboarding hook uses — `provision.auto_provision_workspace`
(the legacy per-user signUp path) — NOT the admin-provisioner path. So run it while the
instance is in the legacy flow (IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=false, apex
unlocked), which provisions successfully.

Idempotent + safe to re-run: a user already in `crm_client_workspaces` is skipped, and
`auto_provision_workspace` is itself idempotent. Per-user failures never stop the run.

Usage (from the Render shell):
    python -m backend.scripts.backfill_crm_workspaces --dry-run        # list who WOULD be provisioned
    python -m backend.scripts.backfill_crm_workspaces                  # provision them
    python -m backend.scripts.backfill_crm_workspaces --limit 5        # cap how many to attempt
    python -m backend.scripts.backfill_crm_workspaces --user-id user_<hex>   # just one

Requires (Jarvis env): SUPABASE_URL (or NEXT_PUBLIC_SUPABASE_URL) + SUPABASE_SERVICE_ROLE_KEY,
plus the same TWENTY_PROVISION_BASE_URL/TWENTY_SERVICE_* the onboarding flow uses.
"""
import argparse
import asyncio
import os

import httpx

import backend.utils.env  # noqa: F401 — loads .env before any module reads env vars

from backend.lib.business.twenty import provision, workspaces

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Transient (network-ish) errors worth retrying; anything else is treated as terminal.
_TRANSIENT_HINTS = ("request failed", "timeout", "timed out", "temporarily", "connection", "503", "502", "504")


def _headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}


async def _fetch_business_users(user_id: str | None = None) -> list[dict]:
    """Every user who completed business onboarding (the canonical source: business_users)."""
    params = {"select": "user_id,company_name,email", "order": "created_at.asc"}
    if user_id:
        params["user_id"] = f"eq.{user_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SUPABASE_URL}/rest/v1/business_users", headers=_headers(), params=params, timeout=30.0)
    resp.raise_for_status()
    return [r for r in resp.json() if (r.get("user_id") or "").strip()]


async def _provisioned_uuids() -> set[str]:
    """All user_ids already in crm_client_workspaces (any status), as stored (uuid)."""
    return {r["user_id"] for r in await workspaces.list_workspaces() if r.get("user_id")}


def select_candidates(business_users: list[dict], provisioned_uuids: set[str]) -> tuple[list[dict], int]:
    """Split onboarded users into (needs-provisioning, already-provisioned-count). Pure."""
    candidates, already = [], 0
    for u in business_users:
        if workspaces._user_id_to_uuid(u["user_id"]) in provisioned_uuids:
            already += 1
        else:
            candidates.append(u)
    return candidates, already


async def _provision_one(user_id: str, display_name: str, retries: int) -> tuple[str, str]:
    """Provision one user with retry on transient errors. Returns (outcome, detail)."""
    last_error = ""
    for attempt in range(1, retries + 2):
        res = await provision.auto_provision_workspace(user_id, display_name or "Jarvis CRM")
        if res.ok:
            if res.data.get("already_provisioned"):
                return "skipped", "already had a workspace"
            return "provisioned", res.data.get("base_url") or "ok"
        last_error = res.error or "unknown error"
        if not any(h in last_error.lower() for h in _TRANSIENT_HINTS):
            return "failed", last_error            # terminal — don't waste retries
        if attempt <= retries:
            await asyncio.sleep(min(2 * attempt, 8))
    return "failed", last_error


async def run_backfill(*, user_id: str | None, dry_run: bool, limit: int | None, retries: int) -> dict:
    users = await _fetch_business_users(user_id)
    provisioned = await _provisioned_uuids()
    candidates, already = select_candidates(users, provisioned)
    if limit is not None:
        candidates = candidates[:limit]

    print(f"Business users: {len(users)} | already provisioned: {already} | to attempt: {len(candidates)}"
          + (" (dry-run)" if dry_run else ""))

    summary = {"provisioned": 0, "skipped": already, "failed": 0, "failures": []}
    for i, u in enumerate(candidates, 1):
        uid, name = u["user_id"], u.get("company_name") or "Jarvis CRM"
        label = f"[{i}/{len(candidates)}] {uid} ({name})"
        if dry_run:
            print(f"WOULD PROVISION {label}")
            continue
        outcome, detail = await _provision_one(uid, name, retries)
        if outcome == "provisioned":
            summary["provisioned"] += 1; print(f"OK   {label} -> {detail}")
        elif outcome == "skipped":
            summary["skipped"] += 1; print(f"SKIP {label} -> {detail}")
        else:
            summary["failed"] += 1; summary["failures"].append((uid, detail)); print(f"FAIL {label} -> {detail}")

    print("\n-- Summary ------------------------------")
    if dry_run:
        print(f"  would provision : {len(candidates)}")
        print(f"  already skipped : {already}")
    else:
        print(f"  provisioned     : {summary['provisioned']}")
        print(f"  skipped         : {summary['skipped']}")
        print(f"  failed          : {summary['failed']}")
        for uid, err in summary["failures"]:
            print(f"    - {uid}: {err}")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill CRM workspaces for existing business users (idempotent).")
    p.add_argument("--dry-run", action="store_true", help="List who WOULD be provisioned; make no changes.")
    p.add_argument("--limit", type=int, default=None, help="Attempt at most N unprovisioned users.")
    p.add_argument("--user-id", default=None, help="Backfill a single user (user_<hex> or uuid).")
    p.add_argument("--retries", type=int, default=2, help="Retries per user on transient errors (default 2).")
    args = p.parse_args()

    if not (SUPABASE_URL and SUPABASE_KEY):
        print("ERROR: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY must be set.")
        return 1

    summary = asyncio.run(run_backfill(user_id=args.user_id, dry_run=args.dry_run, limit=args.limit, retries=args.retries))
    return 1 if summary.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
