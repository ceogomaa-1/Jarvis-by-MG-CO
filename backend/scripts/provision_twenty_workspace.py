"""
Provision a per-client Jarvis CRM workspace (Phase 2 multi-tenant).

Registers a client's own data-isolated Twenty workspace against their Jarvis user_id
so Jarvis resolves the right workspace per client (crm_client_workspaces).

Recommended flow per client:
  1. In Twenty (multi-workspace enabled), create the client's workspace and pick a
     subdomain, e.g. acme → https://acme.crm.jarvismgco.com
  2. In that workspace: Settings → API & Webhooks → Create Key. Copy it once.
  3. Register it against the client's Jarvis user_id:

       python -m backend.scripts.provision_twenty_workspace \
         --user-id <uuid> \
         --base-url https://acme.crm.jarvismgco.com \
         --api-key <workspace key> \
         --display-name "Acme Realty"

     (--subdomain is inferred from the workspace if omitted.)

  4. Then import their GHL data INTO that workspace:
       python -m backend.scripts.import_ghl_to_twenty --user-id <uuid>
     (the importer resolves the same per-user workspace automatically.)

Verify what's registered:
  python -m backend.scripts.provision_twenty_workspace --list

Requires (Jarvis env): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import argparse
import asyncio
import json

import backend.utils.env  # noqa: F401 — loads .env before any module reads env vars

from backend.lib.business.twenty import provision, workspaces


async def _register(args: argparse.Namespace) -> int:
    res = await provision.register_workspace(
        args.user_id,
        base_url=args.base_url,
        api_key=args.api_key,
        subdomain=args.subdomain,
        display_name=args.display_name,
        apply_branding=not args.no_branding,
    )
    if not res.ok:
        print(f"ERROR: {res.error}")
        return 1
    print("Workspace registered:")
    print(json.dumps(res.data, indent=2))
    print("\nNext: import their GHL data ->")
    print(f"  python -m backend.scripts.import_ghl_to_twenty --user-id {args.user_id}")
    return 0


async def _auto(args: argparse.Namespace) -> int:
    res = await provision.auto_provision_workspace(args.user_id, args.display_name or "Jarvis CRM")
    if not res.ok:
        print(f"ERROR: {res.error}")
        return 1
    if res.data.get("already_provisioned"):
        print(f"User {args.user_id} already has a workspace — nothing to do.")
        return 0
    print(f"Auto-provisioned workspace {res.data.get('base_url')} (id {res.data.get('workspace_id')}).")
    return 0


async def _list() -> int:
    rows = await workspaces.list_workspaces()
    if not rows:
        print("No client workspaces registered yet.")
        return 0
    print(f"{len(rows)} workspace(s):")
    for r in rows:
        print(json.dumps(r, indent=2, default=str))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Provision/register a per-client Jarvis CRM workspace.")
    p.add_argument("--list", action="store_true", help="List registered client workspaces and exit.")
    p.add_argument("--auto", action="store_true", help="Auto-provision a NEW isolated workspace for --user-id (Option A; needs multi-workspace enabled).")
    p.add_argument("--user-id", help="Jarvis user_id (uuid or user_<hex>) to register the workspace for.")
    p.add_argument("--base-url", help="Workspace API base URL, e.g. https://acme.crm.jarvismgco.com")
    p.add_argument("--api-key", help="Workspace-scoped API key (Settings → API & Webhooks).")
    p.add_argument("--subdomain", default=None, help="Workspace subdomain (inferred if omitted).")
    p.add_argument("--display-name", default=None, help="Client-facing workspace name, e.g. 'Acme Realty'.")
    p.add_argument("--no-branding", action="store_true", help="Skip pushing Jarvis CRM workspace defaults.")
    args = p.parse_args()

    if args.list:
        return asyncio.run(_list())

    if args.auto:
        if not args.user_id:
            p.error("--user-id required with --auto.")
        return asyncio.run(_auto(args))

    missing = [f for f in ("user_id", "base_url", "api_key") if not getattr(args, f.replace("-", "_"))]
    if missing:
        p.error(f"--{', --'.join(m.replace('_', '-') for m in missing)} required (or use --list).")

    return asyncio.run(_register(args))


if __name__ == "__main__":
    raise SystemExit(main())
