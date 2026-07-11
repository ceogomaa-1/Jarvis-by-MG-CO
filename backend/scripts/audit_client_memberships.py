"""
Audit every active client Twenty workspace for the missing-member lockout.

For each registered workspace it lists the workspace members and flags any workspace whose
ONLY members are service identities (crm+...@ / the shared provisioner) — i.e. no real
client member, which means that client gets "User does not have access" at their subdomain.

Run from an environment that can reach Twenty + has the Rue Supabase service-role env.

  python -m backend.scripts.audit_client_memberships

Requires: SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import asyncio
import json

import backend.utils.env  # noqa: F401

from backend.lib.business.twenty import membership, workspaces
from backend.lib.business.twenty.client import TwentyClient


def _is_service_email(email: str) -> bool:
    e = (email or "").lower()
    return e.startswith("crm+") or "provision" in e


async def _run() -> int:
    rows = await workspaces.list_workspaces_with_keys()
    active = [r for r in rows if (r.get("status") == "active") and r.get("base_url") and r.get("api_key")]
    if not active:
        print("No active client workspaces registered.")
        return 0

    out = []
    gaps = 0
    for r in active:
        client = TwentyClient(r["base_url"], r["api_key"])
        entry = {
            "user_id": r.get("user_id"),
            "subdomain": r.get("subdomain"),
            "display_name": r.get("display_name"),
            "base_url": r.get("base_url"),
        }
        ping = await client.ping()
        if not ping.ok:
            entry["reachable"] = False
            entry["error"] = ping.error
            out.append(entry)
            continue
        members, err = await membership.workspace_member_emails(client)
        if err:
            entry["members_error"] = err
            out.append(entry)
            continue
        real_members = sorted(m for m in members if not _is_service_email(m))
        service_members = sorted(m for m in members if _is_service_email(m))
        entry["real_members"] = real_members
        entry["service_members"] = service_members
        entry["has_client_member"] = bool(real_members)
        if not real_members:
            gaps += 1
            entry["GAP"] = "no real client member — client is locked out"
        out.append(entry)

    print(json.dumps({"active_workspaces": len(active), "missing_client_member": gaps, "workspaces": out},
                     indent=2, default=str))
    if gaps:
        print(f"\n{gaps} workspace(s) have NO real client member. Repair each:")
        print("  python -m backend.scripts.repair_client_membership --user-id <uuid> --client-email <client email>")
    else:
        print("\nAll active workspaces have at least one real client member.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
