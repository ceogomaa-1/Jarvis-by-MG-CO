"""
Repair a client's Twenty workspace access (membership + clean CRM).

Fixes the "User does not have access to this workspace" lockout: the workspace was created
under a service identity and the real client was never added as a member. This:

  1. resolves the client's workspace from the registry (or --base-url/--api-key),
  2. wipes the demo/seed data so they open a clean CRM,
  3. adds the client email as a workspace member (invitation → password-setup email),
  4. VERIFIES the client is present, and
  5. reconciles crm_provisioning_jobs: 'done' only if verified, else 'pending' with the reason.

Run from an environment that can reach the Twenty apex/subdomain and has the Jarvis
Supabase service-role env (i.e. Render shell).

Property Partners RE:
  python -m backend.scripts.repair_client_membership \
    --user-id 7ec1625c-6165-440b-bb42-39e72710dc54 \
    --client-email jon@propertypartnersrealestate.ca \
    --wipe-all

Requires (Jarvis env): SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import argparse
import asyncio
import json

import backend.utils.env  # noqa: F401 — load .env first

from backend.lib.business.twenty import membership, workspaces
from backend.lib.business.twenty.client import TwentyClient


async def _run(args: argparse.Namespace) -> int:
    if args.base_url and args.api_key:
        base_url, api_key = args.base_url, args.api_key
        row = {"base_url": base_url, "api_key": api_key}
    else:
        row = await workspaces.get_workspace(args.user_id)
        if not row:
            print(f"ERROR: no active workspace registered for {args.user_id}. "
                  f"Pass --base-url and --api-key explicitly.")
            return 1
        base_url, api_key = row["base_url"], row["api_key"]

    client = TwentyClient(base_url, api_key)
    report: dict = {"user_id": args.user_id, "base_url": base_url, "client_email": args.client_email}

    ping = await client.ping()
    if not ping.ok:
        print(f"ERROR: workspace unreachable with stored key: {ping.error}")
        return 1

    # 1. members before
    before, err = await membership.workspace_member_emails(client)
    report["members_before"] = sorted(before)
    if err:
        report["members_before_error"] = err

    # 2. wipe seed
    wipe = await membership.wipe_seed_data(client, wipe_all=args.wipe_all)
    report["seed_wipe"] = wipe

    # 3. add the client as a member
    report["invite"] = await membership.ensure_client_membership(client, args.client_email)

    # 4. verify
    verified, status = await membership.verify_client_member(client, args.client_email)
    report["verified"] = verified
    report["member_status"] = status
    after, _ = await membership.workspace_member_emails(client)
    report["members_after"] = sorted(after)

    # 5. reconcile the provisioning job to the TRUTH
    if args.user_id:
        if verified:
            await workspaces.upsert_job(args.user_id, status="done", last_error="")
        else:
            await workspaces.upsert_job(
                args.user_id, status="pending",
                last_error=f"client {args.client_email} not confirmed as member (invite={report['invite'].get('status')}, verify={status})",
            )

    print(json.dumps(report, indent=2, default=str))
    if not verified:
        print("\nNOT VERIFIED. If invite=invite_failed, the invitation mutation name differs on "
              "this Twenty version — share the error above and we'll pin the exact mutation. "
              "If invite=invited, the client must accept the emailed invite (check SMTP).")
        return 2
    print(f"\nOK: {args.client_email} is now '{status}' in the workspace. "
          f"They can log in at {base_url}.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Repair a client's Twenty workspace membership + clean seed data.")
    p.add_argument("--user-id", required=True, help="Jarvis user_id (uuid or user_<hex>).")
    p.add_argument("--client-email", required=True, help="The client's login email to add as a member.")
    p.add_argument("--base-url", default=None, help="Override workspace base URL (else resolved from registry).")
    p.add_argument("--api-key", default=None, help="Override workspace API key (else resolved from registry).")
    p.add_argument("--wipe-all", action="store_true",
                   help="Delete ALL records (safe only for a never-used workspace). Default wipes the demo company set only.")
    return asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
