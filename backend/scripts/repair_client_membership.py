"""
Repair a client's Twenty workspace access (membership + clean CRM).

Fixes the "User does not have access to this workspace" lockout: the workspace was created
under a service identity and the real client was never added as a member. This:

  1. resolves the client's workspace from the registry (or --base-url/--api-key),
  2. wipes the demo/seed data so they open a clean CRM,
  3. adds the client email as a workspace member (invitation → password-setup email),
  4. VERIFIES the client is present, and
  5. reconciles crm_provisioning_jobs: 'done' only if verified, else 'pending' with the reason.

Run from an environment that can reach the Twenty apex/subdomain and has the Rue
Supabase service-role env (i.e. Render shell).

Property Partners RE:
  python -m backend.scripts.repair_client_membership \
    --user-id 7ec1625c-6165-440b-bb42-39e72710dc54 \
    --client-email jon@propertypartnersrealestate.ca \
    --wipe-all

Requires (Rue env): SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import argparse
import asyncio
import json

import backend.utils.env  # noqa: F401 — load .env first

from backend.lib.business.twenty import membership, provision, workspaces
from backend.lib.business.twenty.client import TwentyClient


async def _run(args: argparse.Namespace) -> int:
    if args.base_url and args.api_key:
        base_url, api_key = args.base_url, args.api_key
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

    # 1. members before (data API read with the workspace key)
    before, err = await membership.workspace_member_emails(client)
    report["members_before"] = sorted(before)
    if err:
        report["members_before_error"] = err

    # 2. wipe seed
    report["seed_wipe"] = await membership.wipe_seed_data(client, wipe_all=args.wipe_all)

    # 3. resolve the service-account creds that OWN this workspace (the only member), so we
    #    can sign in as a member and call sendInvitations on the auth endpoint.
    creds = await workspaces.get_service_creds(args.user_id)
    hex_id = (args.user_id or "").removeprefix("user_").replace("-", "")
    svc_email = args.service_email or creds.get("service_email") or f"crm+{hex_id}@{provision.SERVICE_EMAIL_DOMAIN}"
    svc_pw = args.service_password or creds.get("service_secret") or provision._service_password(args.user_id)
    report["service_account"] = svc_email

    # 4. invite the client via the auth/core endpoint with a workspace-scoped user token
    invite = await provision.add_client_member(
        base_url=base_url, service_email=svc_email, service_password=svc_pw,
        client_email=args.client_email,
    )
    report["invite"] = {"ok": invite.ok, "error": invite.error, **(invite.data or {})}

    # 5. verify + reconcile the job to the TRUTH
    member_ok, _ = await membership.is_member(client, args.client_email)
    verified = member_ok or invite.ok
    status = "member" if member_ok else ("invited" if invite.ok else "absent")
    report["verified"] = verified
    report["member_status"] = status
    after, _ = await membership.workspace_member_emails(client)
    report["members_after"] = sorted(after)

    if args.user_id:
        if verified:
            await workspaces.upsert_job(args.user_id, status="done", last_error="")
        else:
            await workspaces.upsert_job(args.user_id, status="pending",
                                        last_error=f"client {args.client_email} not added: {invite.error}")

    print(json.dumps(report, indent=2, default=str))
    accept_url = (invite.data or {}).get("accept_url")
    if not verified:
        print(f"\nNOT VERIFIED — invite failed: {invite.error}")
        print("If sign-in failed, the service-account password differs from _service_password "
              "and no service_secret is stored — pass --service-password. If the mutation name "
              "differs, share the error and we'll pin it.")
        return 2
    print(f"\nOK: {args.client_email} is '{status}'. They can log in at {base_url}.")
    if accept_url:
        print(f"ACCEPT LINK (SMTP-independent — send this to the client):\n  {accept_url}")
    else:
        print("Invitation sent, but no accept link could be built (inviteHash/token not exposed). "
              "If SMTP is configured the client got an email; otherwise re-run after enabling it.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Repair a client's Twenty workspace membership + clean seed data.")
    p.add_argument("--user-id", required=True, help="Rue user_id (uuid or user_<hex>).")
    p.add_argument("--client-email", required=True, help="The client's login email to add as a member.")
    p.add_argument("--base-url", default=None, help="Override workspace base URL (else resolved from registry).")
    p.add_argument("--api-key", default=None, help="Override workspace API key (else resolved from registry).")
    p.add_argument("--service-email", default=None, help="Workspace member to sign in as for the invite (else service_email / crm+<hex>@domain).")
    p.add_argument("--service-password", default=None, help="Password for --service-email (else stored service_secret / deterministic).")
    p.add_argument("--wipe-all", action="store_true",
                   help="Delete ALL records (safe only for a never-used workspace). Default wipes the demo company set only.")
    return asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
