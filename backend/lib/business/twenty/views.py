"""
Step 5 — recreate the GHL layout as Twenty views.

  - A Kanban Opportunity view per GHL pipeline, grouped by that pipeline's stage
    field (stages already created in GHL order by schema_mirror) — this is the
    "same board" win.
  - Table views for People and Opportunities exposing the imported custom fields
    as columns.

Views are version-sensitive in Twenty, so every write funnels through `_create_view` /
`_add_view_field` and the whole step is BEST-EFFORT: failures are recorded in the
summary and never abort the import. Honest scope — faithful structure/layout, not
pixel-identical GHL chrome.
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import store
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import TwentySchema

_CREATE_VIEW = """
mutation CreateView($data: ViewCreateInput!) {
  createView(data: $data) { id name }
}
"""

_CREATE_VIEW_FIELD = """
mutation CreateViewField($data: ViewFieldCreateInput!) {
  createViewField(data: $data) { id }
}
"""


async def _create_view(client: TwentyClient, data: dict, summary: dict) -> str | None:
    res = await client.query_data(_CREATE_VIEW, {"data": data}, action=f"Create view {data.get('name')}")
    if not res.ok:
        summary["errors"].append(f"view {data.get('name')}: {res.error}")
        return None
    vid = ((res.data or {}).get("createView") or {}).get("id")
    summary["views_created"] += 1 if vid else 0
    return vid


async def _add_view_field(client: TwentyClient, view_id: str, field_id: str, position: int, summary: dict):
    res = await client.query_data(
        _CREATE_VIEW_FIELD,
        {"data": {"viewId": view_id, "fieldMetadataId": field_id, "position": position, "isVisible": True}},
        action="Add view column",
    )
    if not res.ok:
        summary["errors"].append(f"view field {field_id}: {res.error}")


async def create_views(client: TwentyClient, schema: TwentySchema, user_id: str, structure: dict, *, dry_run: bool = False) -> dict:
    summary = {"views_created": 0, "errors": []}
    if dry_run:
        summary["note"] = "dry-run: views not created"
        return summary

    struct_map = await store.load_structure_map(user_id)
    person = schema.obj("person")
    opportunity = schema.obj("opportunity")

    # ── Kanban board per pipeline, grouped by its stage field ─────────────────
    for pipe in structure.get("pipelines", []):
        row = struct_map.get(("pipeline", pipe["id"]))
        if not row or not opportunity:
            continue
        stage_field_id = row["twenty_id"]
        await _create_view(client, {
            "name": f"{pipe['name']} — Board",
            "objectMetadataId": opportunity.id,
            "type": "KANBAN",
            "kanbanFieldMetadataId": stage_field_id,
        }, summary)

    # ── People table (name/email + custom person fields) ──────────────────────
    if person:
        person_field_ids = [
            r["twenty_id"] for (k, _), r in struct_map.items()
            if k == "custom_field" and (r.get("extra") or {}).get("object") == "person"
        ]
        view_id = await _create_view(client, {
            "name": "People", "objectMetadataId": person.id, "type": "TABLE",
        }, summary)
        if view_id:
            for i, fid in enumerate(person_field_ids):
                await _add_view_field(client, view_id, fid, i, summary)

    # ── Opportunities table (custom opp fields as columns) ────────────────────
    if opportunity:
        opp_field_ids = [
            r["twenty_id"] for (k, _), r in struct_map.items()
            if k == "custom_field" and (r.get("extra") or {}).get("object") == "opportunity"
        ]
        # include the stage fields too
        opp_field_ids += [r["twenty_id"] for (k, _), r in struct_map.items() if k == "pipeline"]
        view_id = await _create_view(client, {
            "name": "Opportunities", "objectMetadataId": opportunity.id, "type": "TABLE",
        }, summary)
        if view_id:
            for i, fid in enumerate(opp_field_ids):
                await _add_view_field(client, view_id, fid, i, summary)

    return summary
