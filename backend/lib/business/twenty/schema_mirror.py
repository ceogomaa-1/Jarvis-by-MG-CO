"""
Step 3 — mirror a client's GHL structure into Twenty, BEFORE importing data.

Creates, in Twenty's metadata API:
  - one SELECT field on Opportunity per GHL pipeline, options = the pipeline's
    stages in GHL order (this is what the Kanban board groups by);
  - matching custom fields on Person / Opportunity (GHL field names preserved,
    types mapped via field_map);
  - a MULTI_SELECT `ghlTags` field on Person carrying GHL tags as options.

Persists a structure map (crm_structure_map) so the importer can place records in
the right stage / populate the right field, and so re-runs reuse existing ids.

All metadata writes funnel through `_create_field` / `_update_field_options`, so if
a Twenty version wants a slightly different mutation shape, there's ONE place to fix.
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import field_map, store
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import TwentyField, TwentyObject, TwentySchema
from backend.lib.business.twenty.naming import to_camel, to_option_value

# Twenty option colors — cycled by position so boards look organized, not monochrome.
_PALETTE = ["green", "turquoise", "sky", "blue", "purple", "pink", "red", "orange", "yellow", "gray"]

# GHL custom-field "model" -> Twenty object alias.
_MODEL_TO_ALIAS = {"contact": "person", "opportunity": "opportunity"}

_CREATE_FIELD = """
mutation CreateField($input: CreateOneFieldMetadataInput!) {
  createOneField(input: $input) { id name type }
}
"""

_UPDATE_FIELD = """
mutation UpdateField($input: UpdateOneFieldMetadataInput!) {
  updateOneField(input: $input) { id name }
}
"""


def _options_payload(labels: list[str]) -> list[dict]:
    """Build Twenty SELECT options (value/label/color/position) from labels, in order."""
    out, seen = [], set()
    for i, label in enumerate(labels):
        value = to_option_value(label, fallback=f"OPTION_{i}")
        # de-dupe values (distinct labels can collapse to the same token)
        base, n = value, 1
        while value in seen:
            value = f"{base}_{n}"
            n += 1
        seen.add(value)
        out.append({
            "value": value,
            "label": label,
            "color": _PALETTE[i % len(_PALETTE)],
            "position": i,
        })
    return out


async def _create_field(
    client: TwentyClient,
    *,
    object_id: str,
    name: str,
    label: str,
    field_type: str,
    options: list[dict] | None = None,
) -> ConnectorResult:
    field_input: dict = {
        "name": name,
        "label": label,
        "type": field_type,
        "objectMetadataId": object_id,
    }
    if options is not None:
        field_input["options"] = options
    return await client.query_meta(
        _CREATE_FIELD, {"input": {"field": field_input}}, action=f"Create field {name}"
    )


async def _update_field_options(client: TwentyClient, field_id: str, options: list[dict]) -> ConnectorResult:
    return await client.query_meta(
        _UPDATE_FIELD,
        {"input": {"id": field_id, "update": {"options": options}}},
        action="Update field options",
    )


def _resolve_type(schema: TwentySchema, twenty_type: str) -> str:
    """Degrade to TEXT if the running Twenty doesn't accept the target type."""
    return twenty_type if schema.supports_type(twenty_type) else field_map.DEFAULT_TYPE


async def _ensure_field(
    client: TwentyClient,
    obj: TwentyObject,
    *,
    name: str,
    label: str,
    field_type: str,
    options: list[dict] | None,
    summary: dict,
    dry_run: bool,
) -> str | None:
    """
    Return the Twenty field id, creating it if absent. Idempotent: if the object
    already has a field with this camel name, reuse it (and top up SELECT options).
    """
    existing = obj.field_by_name(name)
    if existing:
        if options and field_type in field_map.OPTION_TYPES and not dry_run:
            # Merge any new options onto the pre-existing field.
            have = {o.get("value") for o in (existing.options or [])}
            merged = list(existing.options or []) + [o for o in options if o["value"] not in have]
            if len(merged) != len(existing.options or []):
                await _update_field_options(client, existing.id, merged)
        summary["fields_reused"] += 1
        return existing.id

    if dry_run:
        summary["fields_would_create"] += 1
        return None

    res = await _create_field(
        client, object_id=obj.id, name=name, label=label, field_type=field_type, options=options
    )
    if not res.ok:
        summary["errors"].append(f"field {name}: {res.error}")
        return None
    field_id = ((res.data or {}).get("createOneField") or {}).get("id")
    if field_id:
        # keep the introspection cache consistent so a second _ensure_field for the
        # same name within this run reuses it instead of creating a duplicate
        obj.fields.append(TwentyField(
            id=field_id, name=name, label=label, type=field_type, is_custom=True, options=options or [],
        ))
        summary["fields_created"] += 1
    return field_id


async def mirror_structure(
    client: TwentyClient,
    schema: TwentySchema,
    user_id: str,
    structure: dict,
    *,
    dry_run: bool = False,
) -> dict:
    """
    Mirror GHL pipelines/stages, custom fields and tags into Twenty.
    Returns a summary dict and persists the structure map.
    """
    summary = {
        "fields_created": 0, "fields_reused": 0, "fields_would_create": 0,
        "pipelines": 0, "stages": 0, "tags": 0, "errors": [],
    }
    person = schema.obj("person")
    opportunity = schema.obj("opportunity")
    if not person or not opportunity:
        summary["errors"].append("Missing Person/Opportunity objects in Twenty schema")
        return summary

    # ── pipelines -> stage SELECT field per pipeline ──────────────────────────
    for pipe in structure.get("pipelines", []):
        stages = pipe.get("stages") or []
        if not stages:
            continue
        field_name = to_camel(f"stage {pipe['name']}", fallback="stage")
        options = _options_payload([s["name"] for s in stages])
        field_id = await _ensure_field(
            client, opportunity,
            name=field_name, label=f"Stage — {pipe['name']}",
            field_type=_resolve_type(schema, "SELECT"), options=options,
            summary=summary, dry_run=dry_run,
        )
        # map each stage id -> its option value, and the pipeline -> its field
        stage_value_by_id = {}
        for opt, st in zip(options, stages):
            stage_value_by_id[st["id"]] = opt["value"]
            if not dry_run:
                await store.upsert_structure(
                    user_id, "stage", st["id"], opt["value"],
                    extra={"pipeline_id": pipe["id"], "field_name": field_name, "label": st["name"]},
                )
            summary["stages"] += 1
        if field_id and not dry_run:
            await store.upsert_structure(
                user_id, "pipeline", pipe["id"], field_id,
                extra={"field_name": field_name, "stage_value_by_id": stage_value_by_id},
            )
        summary["pipelines"] += 1

    # ── custom fields -> Person / Opportunity fields ──────────────────────────
    for cf in structure.get("custom_fields", []):
        model = (cf.get("model") or "contact").lower()
        alias = _MODEL_TO_ALIAS.get(model, "person")
        obj = schema.obj(alias)
        if not obj:
            continue
        label = cf.get("name") or "Custom Field"
        name = to_camel(label, fallback="customField")
        ttype = _resolve_type(schema, field_map.ghl_type_to_twenty(cf.get("dataType")))
        options = None
        if field_map.needs_options(ttype):
            options = _options_payload(field_map.extract_ghl_options(cf))
            if not options:  # SELECT with no options isn't valid — fall back to text
                ttype = field_map.DEFAULT_TYPE
        field_id = await _ensure_field(
            client, obj, name=name, label=label, field_type=ttype,
            options=options, summary=summary, dry_run=dry_run,
        )
        if field_id and not dry_run:
            value_by_label = {o["label"]: o["value"] for o in (options or [])}
            await store.upsert_structure(
                user_id, "custom_field", cf.get("id") or name, field_id,
                extra={"object": alias, "field_name": name, "type": ttype, "value_by_label": value_by_label},
            )

    # ── tags -> Person.ghlTags MULTI_SELECT ───────────────────────────────────
    tags = structure.get("tags", [])
    if tags:
        tag_labels = [t.get("name") for t in tags if t.get("name")]
        options = _options_payload(tag_labels)
        field_id = await _ensure_field(
            client, person, name="ghlTags", label="Tags",
            field_type=_resolve_type(schema, "MULTI_SELECT"), options=options,
            summary=summary, dry_run=dry_run,
        )
        value_by_label = {o["label"]: o["value"] for o in options}
        if field_id and not dry_run:
            for t in tags:
                if t.get("name"):
                    await store.upsert_structure(
                        user_id, "tag", t.get("id") or t["name"], value_by_label.get(t["name"], ""),
                        extra={"field_name": "ghlTags", "label": t["name"]},
                    )
                    summary["tags"] += 1
    return summary
