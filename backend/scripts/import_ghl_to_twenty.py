"""
Import a client's GoHighLevel CRM into the Rue-owned Twenty instance.

Runs the full Phase-1 pipeline in order:
  Step 2  introspect Twenty's live schema (logs the real objects + fields)
  Step 3  mirror GHL structure (pipelines/stages, custom fields, tags) into Twenty
  Step 4  import the data (idempotent + resumable)
  Step 5  create the views (Kanban board per pipeline + table views)

Idempotent: re-running makes zero duplicate records (crm_import_map) and reuses
existing fields (crm_structure_map). GoHighLevel is only ever read.

Usage:
    python -m backend.scripts.import_ghl_to_twenty --user-id <uuid> [--account-label default]
    python -m backend.scripts.import_ghl_to_twenty --user-id <uuid> --dry-run
    python -m backend.scripts.import_ghl_to_twenty --user-id <uuid> --max-records 50   # quick smoke test

Requires (in the Rue env): TWENTY_API_URL, TWENTY_API_KEY, SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY, and the user must have a GoHighLevel connection.
"""
import argparse
import asyncio
import json

import backend.utils.env  # noqa: F401 — loads .env before any module reads env vars

from backend.lib.business.twenty import ghl_reader, importer as importer_mod, schema_mirror, views
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import introspect, log_schema


async def _run(user_id: str, account_label: str, dry_run: bool, max_records: int | None) -> int:
    # Resolve the client's OWN workspace (Phase 2) — imports land in their tenant,
    # not the shared instance. Falls back to env (Phase 1) if they have no workspace.
    client = await TwentyClient.for_user(user_id)
    if not client:
        print("ERROR: No Rue CRM workspace for this user and no shared instance configured.")
        print("       Register one first:  python -m backend.scripts.provision_twenty_workspace --user-id "
              f"{user_id} --base-url <url> --api-key <key>")
        print("       (or set TWENTY_API_URL + TWENTY_API_KEY for the single shared instance).")
        return 1

    # Step 2 — introspect (no guessing)
    print("> Step 2: introspecting Twenty schema...")
    schema_res = await introspect(client)
    if not schema_res.ok:
        print(f"ERROR: Schema introspection failed: {schema_res.error}")
        return 1
    schema = schema_res.data
    log_schema(schema)

    # GHL connector
    ghl = await ghl_reader.get_ghl(user_id, account_label)
    if not ghl:
        print(f"ERROR: User {user_id} has no active GoHighLevel connection (label={account_label}).")
        return 1

    # Read GHL structure
    print("> Reading GoHighLevel structure...")
    struct_res = await ghl_reader.read_structure(ghl)
    structure = struct_res.data or {}
    for w in structure.get("warnings", []):
        print(f"  ! {w}")
    print(f"  pipelines={len(structure.get('pipelines', []))} "
          f"custom_fields={len(structure.get('custom_fields', []))} tags={len(structure.get('tags', []))}")

    # Step 3 — mirror structure
    print(f"> Step 3: mirroring structure into Twenty{' (dry-run)' if dry_run else ''}...")
    mirror_summary = await schema_mirror.mirror_structure(client, schema, user_id, structure, dry_run=dry_run)
    print("  " + json.dumps(mirror_summary))

    # Re-introspect so the importer sees the fields just created
    if not dry_run:
        schema = (await introspect(client)).data or schema

    # Step 4 — import data
    print(f"> Step 4: importing data{' (dry-run)' if dry_run else ''}...")
    imp = importer_mod.Importer(client, schema, user_id, dry_run=dry_run, max_records=max_records)
    import_summary = await imp.run(ghl, structure)
    print("  " + json.dumps(import_summary, default=str))

    # Step 5 — views
    print(f"> Step 5: creating views{' (dry-run)' if dry_run else ''}...")
    view_summary = await views.create_views(client, schema, user_id, structure, dry_run=dry_run)
    print("  " + json.dumps(view_summary))

    errors = mirror_summary.get("errors", []) + import_summary.get("errors", []) + view_summary.get("errors", [])
    print("\nOK. Done." + (f" {len(errors)} error(s) — see above." if errors else " No errors."))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Import GoHighLevel into the Rue-owned Twenty CRM.")
    ap.add_argument("--user-id", help="Rue user id whose GHL connection to import")
    ap.add_argument("--account-label", default="default", help="Which connected GHL account (default: default)")
    ap.add_argument("--dry-run", action="store_true", help="Plan only — no writes to Twenty")
    ap.add_argument("--max-records", type=int, default=None, help="Cap records per type (smoke test)")
    args = ap.parse_args()

    if not args.user_id:
        # Still let --dry-run with no env exit cleanly (verify step).
        if not TwentyClient.configured():
            print("ERROR: Twenty not configured (TWENTY_API_URL/TWENTY_API_KEY unset) and no --user-id given. Nothing to do.")
            return 1
        ap.error("--user-id is required")

    return asyncio.run(_run(args.user_id, args.account_label, args.dry_run, args.max_records))


if __name__ == "__main__":
    raise SystemExit(main())
