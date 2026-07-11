"""Deprovision Rue CRM workspaces — free slots under Twenty Community's 5-workspace cap.

Twenty Community caps an instance at 5 workspaces. When throwaway/test workspaces fill the
slots, a real client can't be provisioned. This deletes the junk ones and frees slots.

How it deletes (self-scoped, no admin needed): each workspace row in crm_client_workspaces
holds that workspace's OWN admin API key, and Twenty's `deleteCurrentWorkspace` acts only on
the token's own workspace. So deleting workspace X uses X's key — it is structurally unable to
touch any other tenant. After the Twenty workspace is gone, the registry row is removed.

You pass a KEEP-list (the workspaces to preserve); everything else is deprovisioned.

Usage (from the Render shell, or anywhere with SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY):
    # See exactly what WOULD be deleted (default — makes no changes):
    python -m backend.scripts.deprovision_twenty_workspace \
        --keep user_3363afdc9bca4b88893cf535c62a6687,user_7ec1625c6165440bbb4239e72710dc54

    # Actually delete:
    python -m backend.scripts.deprovision_twenty_workspace --keep <ids...> --execute

    # Repair a kept row whose base_url drifted to the apex (fixes "invalid response"):
    python -m backend.scripts.deprovision_twenty_workspace --repair user_3363afdc... --execute

Notes:
  • --keep accepts user_<hex> or dashed uuids, comma-separated and/or repeated.
  • Orphan Twenty workspaces with NO registry row (failed provisions) can't be reached by key;
    delete those from the Twenty admin panel / provisioner. This tool reports the live count so
    you can tell whether any orphans remain under the cap.
"""
import argparse
import asyncio
import json

import backend.utils.env  # noqa: F401 — loads .env before any module reads env vars

from backend.lib.business.twenty import provision, workspaces


def _norm(uid: str) -> str:
    """Normalise an id to the stored uuid form for comparison."""
    return workspaces._user_id_to_uuid((uid or "").strip())


def _parse_keep(values: list[str] | None) -> set[str]:
    keep: set[str] = set()
    for v in values or []:
        for part in v.split(","):
            if part.strip():
                keep.add(_norm(part))
    return keep


async def _repair(user_id: str, execute: bool) -> int:
    if not execute:
        row = await workspaces.get_workspace(user_id)
        print(f"WOULD REPAIR {user_id}: current base_url={row.get('base_url') if row else '(no row)'}")
        print("(re-run with --execute to apply)")
        return 0
    res = await provision.repair_workspace_identity(user_id)
    if not res.ok:
        print(f"ERROR: {res.error}")
        return 1
    if res.data.get("changed"):
        print(f"REPAIRED {user_id}:")
    else:
        print(f"OK (already correct) {user_id}:")
    print(json.dumps({k: res.data.get(k) for k in ("base_url", "subdomain", "workspace_id")}, indent=2))
    return 0


async def run(*, keep: set[str], execute: bool) -> int:
    rows = await workspaces.list_workspaces_with_keys()
    if not rows:
        print("Registry empty (or Supabase env not set).")
        return 0

    keepers = [r for r in rows if _norm(r.get("user_id")) in keep]
    targets = [r for r in rows if _norm(r.get("user_id")) not in keep]

    print(f"Registry rows: {len(rows)} | keeping: {len(keepers)} | to deprovision: {len(targets)}"
          + ("" if execute else "  (DRY-RUN - no changes)"))
    print("\nKEEP:")
    for r in keepers:
        print(f"  [keep] {r.get('display_name')!r:30} {r.get('user_id')}  {r.get('base_url')}")
    print("\nDEPROVISION:")
    for r in targets:
        print(f"  [del]  {r.get('display_name')!r:30} {r.get('user_id')}  {r.get('base_url')}")

    if not keep:
        print("\nRefusing to run with an EMPTY keep-list (that would delete everything). "
              "Pass --keep <ids>.")
        return 1

    if not execute:
        print("\n(re-run with --execute to delete the above)")
        return 0

    print("\nExecuting…")
    failed = 0
    for r in targets:
        res = await provision.deprovision_workspace(r)
        if res.ok:
            d = res.data
            state = "remote+row deleted" if d["remote_deleted"] else (
                "row deleted (workspace already gone)" if d["already_gone"] else "row deleted")
            print(f"  OK  {d.get('display_name')!r} ({d.get('subdomain')}) -> {state}")
        else:
            failed += 1
            print(f"  FAIL {r.get('display_name')!r}: {res.error}")

    remaining = await workspaces.list_workspaces()
    print(f"\nRegistry now has {len(remaining)} row(s):")
    for r in remaining:
        print(f"  - {r.get('display_name')!r:30} {r.get('subdomain')}  {r.get('base_url')}")
    return 1 if failed else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Deprovision Rue CRM workspaces (keep-list driven).")
    p.add_argument("--keep", action="append", default=[],
                   help="user_id(s) to PRESERVE (user_<hex> or uuid; comma-separated and/or repeated).")
    p.add_argument("--repair", default=None,
                   help="Instead of deleting, repair this user's row identity (base_url/subdomain/workspace_id).")
    p.add_argument("--execute", action="store_true", help="Apply changes (default is a dry-run).")
    args = p.parse_args()

    if args.repair:
        return asyncio.run(_repair(args.repair, args.execute))
    return asyncio.run(run(keep=_parse_keep(args.keep), execute=args.execute))


if __name__ == "__main__":
    raise SystemExit(main())
