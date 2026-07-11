"""
Rue CRM structure-level control (Twenty METADATA API), GUARDED.

Lets a user reshape their CRM by asking Rue: add/update/delete custom fields,
create/delete custom objects ("types"), and build custom lists/views. All mutations
hit the per-user workspace's /metadata endpoint (TwentyClient.for_user → query_meta),
so structure changes are isolated to that tenant.

Schema-driven: object and field ids are resolved by introspecting the live metadata
(no guessed ids). Mutation shapes were confirmed by introspecting the live API:
  fields  → createOneField / updateOneField / deleteOneField  (input wraps {field|update})
  objects → createOneObject / deleteOneObject                 (input wraps {object})
  views   → createView / updateView / deleteView (+ createViewSort/Field/Group)

Guardrails: structural deletes (delete_field/object/view) are listed in chat.py
WRITE_ACTIONS for hold-to-confirm. Every metadata change emits crm_changed so the
cockpit reloads and picks up the new structure. GHL is never touched.
"""
import re

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import fetch_field_type_enum, fetch_objects

# user-facing type word -> Twenty FieldMetadataType
_TYPE_MAP = {
    "text": "TEXT", "string": "TEXT",
    "number": "NUMBER", "numeric": "NUMBER", "int": "NUMBER",
    "currency": "CURRENCY", "money": "CURRENCY",
    "date": "DATE_TIME", "datetime": "DATE_TIME", "date_time": "DATE_TIME",
    "boolean": "BOOLEAN", "bool": "BOOLEAN", "checkbox": "BOOLEAN",
    "select": "SELECT", "dropdown": "SELECT",
    "multi-select": "MULTI_SELECT", "multiselect": "MULTI_SELECT", "multi_select": "MULTI_SELECT", "tags": "MULTI_SELECT",
    "phone": "PHONES", "phones": "PHONES",
    "email": "EMAILS", "emails": "EMAILS",
    "link": "LINKS", "links": "LINKS", "url": "LINKS",
    "rating": "RATING",
}
_NEEDS_OPTIONS = {"SELECT", "MULTI_SELECT"}
_PALETTE = ["green", "turquoise", "sky", "blue", "purple", "pink", "red", "orange", "yellow", "gray"]


def _camel(s: str) -> str:
    words = [w for w in re.split(r"[^a-zA-Z0-9]+", (s or "").strip()) if w]
    if not words:
        return "field"
    return words[0][:1].lower() + words[0][1:] + "".join(w[:1].upper() + w[1:] for w in words[1:])


def _singular(s: str) -> str:
    s = s.strip()
    low = s.lower()
    if low.endswith("ies"):
        return s[:-3] + "y"
    if low.endswith(("ses", "xes", "zes", "ches", "shes")):
        return s[:-2]
    if low.endswith("s") and not low.endswith("ss"):
        return s[:-1]
    return s


def _plural(s: str) -> str:
    low = s.lower()
    if low.endswith("y") and not low.endswith(("ay", "ey", "iy", "oy", "uy")):
        return s[:-1] + "ies"
    if low.endswith(("s", "x", "z", "ch", "sh")):
        return s + "es"
    return s + "s"


def _build_options(opts: list) -> list[dict]:
    out = []
    for i, o in enumerate(opts or []):
        label = str(o).strip()
        value = re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_") or f"OPT_{i}"
        out.append({"label": label, "value": value, "color": _PALETTE[i % len(_PALETTE)], "position": i})
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ── resolution ────────────────────────────────────────────────────────────────
async def _objects(client: TwentyClient) -> list[dict]:
    res = await fetch_objects(client)
    return res.data or [] if res.ok else []


def _find_object(objects: list[dict], name: str) -> dict | None:
    n = _norm(name)
    cam = _norm(_camel(name))
    for o in objects:
        cands = {_norm(o.get(k) or "") for k in ("nameSingular", "namePlural", "labelSingular", "labelPlural")}
        if n in cands or cam in cands:
            return o
    # last resort: singular/plural normalised
    sn = _norm(_singular(name))
    for o in objects:
        if sn and sn == _norm(o.get("nameSingular") or ""):
            return o
    return None


def _find_field(obj: dict, name: str) -> dict | None:
    n = _norm(name)
    for f in obj.get("_fields", []):
        if n == _norm(f.get("name") or "") or n == _norm(f.get("label") or ""):
            return f
    # contains match (e.g. "creation date" → createdAt/Creation Date)
    for f in obj.get("_fields", []):
        if n and (n in _norm(f.get("name") or "") or n in _norm(f.get("label") or "")):
            return f
    return None


async def _resolve_field_type(client: TwentyClient, word: str) -> tuple[str | None, str]:
    ftype = _TYPE_MAP.get((word or "").strip().lower())
    if not ftype:
        return None, f"Unsupported field type '{word}'. Supported: {', '.join(sorted(set(_TYPE_MAP)))}."
    accepted = await fetch_field_type_enum(client)
    if accepted and ftype not in accepted:
        return None, f"This CRM version doesn't accept field type {ftype}."
    return ftype, ""


# ── field creation primitive (shared by create_field + create_object) ───────────
async def _create_field(client: TwentyClient, object_id: str, label: str, ftype: str, options: list | None) -> ConnectorResult:
    base = {"type": ftype, "label": label, "objectMetadataId": object_id, "isNullable": True}
    if ftype in _NEEDS_OPTIONS:
        built = _build_options(options or [])
        if not built:
            return ConnectorResult(ok=False, error=f"Field '{label}' is a {ftype} and needs at least one option.")
        base["options"] = built
    mutation = "mutation CreateField($input: CreateOneFieldMetadataInput!) { createOneField(input: $input) { id name } }"
    # Some names collide with Twenty's reserved/standard field names (e.g. "address",
    # "name"). Retry once with a safe suffix so the create still succeeds.
    for name in (_camel(label), _camel(label) + "Field"):
        res = await client.query_meta(mutation, {"input": {"field": {**base, "name": name}}}, action="Create field")
        if res.ok:
            return ConnectorResult(ok=True, data=((res.data or {}).get("createOneField") or {}))
    return res


# ══ INTROSPECTION (reads) ═════════════════════════════════════════════════════
async def list_objects(client, user_id, inp) -> ConnectorResult:
    objs = await _objects(client)
    rows = []
    for o in objs:
        if inp.get("custom_only") and not o.get("isCustom"):
            continue
        rows.append({
            "object": o.get("namePlural"), "label": o.get("labelPlural"),
            "is_custom": bool(o.get("isCustom")),
            "fields": [{"name": f.get("name"), "label": f.get("label"), "type": f.get("type"), "custom": bool(f.get("isCustom"))}
                       for f in o.get("_fields", [])],
        })
    return ConnectorResult(ok=True, data={"count": len(rows), "objects": rows})


async def list_views(client, user_id, inp) -> ConnectorResult:
    # Views are read via getViews (a flat list on the metadata Query, not a connection).
    res = await client.query_meta(
        "query Views { getViews { id name objectMetadataId type } }",
        action="List views",
    )
    if not res.ok:
        return res
    objs = await _objects(client)
    by_id = {o.get("id"): (o.get("labelPlural") or o.get("namePlural")) for o in objs}
    want_obj = _find_object(objs, inp["object"]) if inp.get("object") else None
    rows = []
    for n in (res.data or {}).get("getViews") or []:
        if want_obj and n.get("objectMetadataId") != want_obj.get("id"):
            continue
        rows.append({"id": n.get("id"), "name": n.get("name"), "type": n.get("type"),
                     "object": by_id.get(n.get("objectMetadataId"))})
    return ConnectorResult(ok=True, data={"count": len(rows), "views": rows})


# ══ CUSTOM FIELDS ═════════════════════════════════════════════════════════════
async def create_field(client, user_id, inp) -> ConnectorResult:
    obj = _find_object(await _objects(client), inp.get("object") or "")
    if not obj:
        return ConnectorResult(ok=False, error=f"No object named '{inp.get('object')}' in this CRM.")
    ftype, err = await _resolve_field_type(client, inp.get("field_type"))
    if not ftype:
        return ConnectorResult(ok=False, error=err)
    label = (inp.get("name") or "").strip()
    if not label:
        return ConnectorResult(ok=False, error="A field needs a name.")
    res = await _create_field(client, obj["id"], label, ftype, inp.get("options"))
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": res.data.get("id"),
                                          "summary": f"Added {ftype} field '{label}' to {obj.get('labelPlural')}."})


async def update_field(client, user_id, inp) -> ConnectorResult:
    obj = _find_object(await _objects(client), inp.get("object") or "")
    if not obj:
        return ConnectorResult(ok=False, error=f"No object named '{inp.get('object')}'.")
    fld = _find_field(obj, inp.get("field") or "")
    if not fld:
        return ConnectorResult(ok=False, error=f"No field '{inp.get('field')}' on {obj.get('labelPlural')}.")
    update: dict = {}
    if inp.get("new_label"):
        update["label"] = inp["new_label"]
    if inp.get("options") is not None:
        update["options"] = _build_options(inp["options"])
    if inp.get("is_active") is not None:
        update["isActive"] = bool(inp["is_active"])
    if not update:
        return ConnectorResult(ok=False, error="Nothing to update (pass new_label, options, or is_active).")
    res = await client.query_meta(
        "mutation UpdateField($input: UpdateOneFieldMetadataInput!) { updateOneField(input: $input) { id } }",
        {"input": {"id": fld["id"], "update": update}}, action="Update field",
    )
    return res if not res.ok else ConnectorResult(ok=True, data={"summary": f"Updated field '{inp.get('field')}' on {obj.get('labelPlural')}."})


async def delete_field(client, user_id, inp) -> ConnectorResult:
    obj = _find_object(await _objects(client), inp.get("object") or "")
    if not obj:
        return ConnectorResult(ok=False, error=f"No object named '{inp.get('object')}'.")
    fld = _find_field(obj, inp.get("field") or "")
    if not fld:
        return ConnectorResult(ok=False, error=f"No field '{inp.get('field')}' on {obj.get('labelPlural')}.")
    if not fld.get("isCustom"):
        return ConnectorResult(ok=False, error=f"'{fld.get('label')}' is a standard field and can't be deleted.")
    res = await client.query_meta(
        "mutation DeleteField($input: DeleteOneFieldInput!) { deleteOneField(input: $input) { id } }",
        {"input": {"id": fld["id"]}}, action="Delete field",
    )
    return res if not res.ok else ConnectorResult(ok=True, data={"status": "deleted", "summary": f"Deleted field '{fld.get('label')}' from {obj.get('labelPlural')}."})


# ══ CUSTOM OBJECTS ════════════════════════════════════════════════════════════
async def create_object(client, user_id, inp) -> ConnectorResult:
    label = (inp.get("name") or "").strip()
    if not label:
        return ConnectorResult(ok=False, error="A new type needs a name (e.g. 'Properties').")
    ls = inp.get("name_singular") or _singular(label)
    lp = inp.get("name_plural") or _plural(ls)
    obj_input = {
        "nameSingular": _camel(ls), "namePlural": _camel(lp),
        "labelSingular": ls[:1].upper() + ls[1:], "labelPlural": lp[:1].upper() + lp[1:],
        "icon": inp.get("icon") or "IconBuildingSkyscraper",
    }
    if _camel(ls) == _camel(lp):
        obj_input["namePlural"] = _camel(lp) + "s"
    res = await client.query_meta(
        "mutation CreateObject($input: CreateOneObjectInput!) { createOneObject(input: $input) { id labelPlural } }",
        {"input": {"object": obj_input}}, action="Create object",
    )
    if not res.ok:
        return res
    new = (res.data or {}).get("createOneObject") or {}
    created_fields, failed = [], []
    for spec in inp.get("fields") or []:
        ftype, err = await _resolve_field_type(client, spec.get("type"))
        if not ftype:
            failed.append(f"{spec.get('name')} ({err})")
            continue
        fr = await _create_field(client, new["id"], (spec.get("name") or "").strip(), ftype, spec.get("options"))
        if fr.ok:
            created_fields.append(spec.get("name"))
        else:
            failed.append(f"{spec.get('name')} ({fr.error})")
    summary = f"Created new type '{new.get('labelPlural')}'"
    if created_fields:
        summary += f" with fields: {', '.join(created_fields)}"
    if failed:
        summary += f" (skipped: {', '.join(str(f) for f in failed)})"
    return ConnectorResult(ok=True, data={"id": new.get("id"), "summary": summary + "."})


async def delete_object(client, user_id, inp) -> ConnectorResult:
    obj = _find_object(await _objects(client), inp.get("name") or inp.get("object") or "")
    if not obj:
        return ConnectorResult(ok=False, error=f"No type named '{inp.get('name') or inp.get('object')}'.")
    if not obj.get("isCustom"):
        return ConnectorResult(ok=False, error=f"'{obj.get('labelPlural')}' is a standard object and can't be deleted.")
    # objects must be deactivated before deletion in Twenty.
    await client.query_meta(
        "mutation Deact($input: UpdateOneObjectInput!) { updateOneObject(input: $input) { id } }",
        {"input": {"id": obj["id"], "update": {"isActive": False}}}, action="Deactivate object",
    )
    res = await client.query_meta(
        "mutation DeleteObject($input: DeleteOneObjectInput!) { deleteOneObject(input: $input) { id } }",
        {"input": {"id": obj["id"]}}, action="Delete object",
    )
    return res if not res.ok else ConnectorResult(ok=True, data={"status": "deleted", "summary": f"Deleted the '{obj.get('labelPlural')}' type."})


# ══ VIEWS / LISTS ═════════════════════════════════════════════════════════════
async def create_view(client, user_id, inp) -> ConnectorResult:
    obj = _find_object(await _objects(client), inp.get("object") or "")
    if not obj:
        return ConnectorResult(ok=False, error=f"No object named '{inp.get('object')}'.")
    vtype = "KANBAN" if (inp.get("view_type") or "table").strip().lower() == "kanban" else "TABLE"
    # icon is REQUIRED by CreateViewInput.
    view: dict = {"name": inp.get("name") or f"{obj.get('labelPlural')} list", "objectMetadataId": obj["id"],
                  "type": vtype, "icon": inp.get("icon") or ("IconLayoutKanban" if vtype == "KANBAN" else "IconLayoutList")}
    # kanban grouping field
    group_summary = ""
    if vtype == "KANBAN":
        gname = inp.get("group_by") or "stage"
        gf = _find_field(obj, gname)
        if gf:
            view["mainGroupByFieldMetadataId"] = gf["id"]
            group_summary = f", grouped by {gf.get('label')}"
    res = await client.query_meta(
        "mutation CreateView($input: CreateViewInput!) { createView(input: $input) { id name } }",
        {"input": view}, action="Create view",
    )
    if not res.ok:
        return res
    vid = ((res.data or {}).get("createView") or {}).get("id")
    # sort
    sort_summary = ""
    if inp.get("sort_by"):
        sf = _find_field(obj, inp["sort_by"])
        if sf:
            direction = "DESC" if (inp.get("sort_direction") or "asc").lower().startswith("d") else "ASC"
            await client.query_meta(
                "mutation Sort($input: CreateViewSortInput!) { createViewSort(input: $input) { id } }",
                {"input": {"viewId": vid, "fieldMetadataId": sf["id"], "direction": direction}}, action="Create view sort",
            )
            sort_summary = f", sorted by {sf.get('label')} {direction}"
    # explicit columns (visible fields)
    for i, col in enumerate(inp.get("columns") or []):
        cf = _find_field(obj, col)
        if cf:
            await client.query_meta(
                "mutation VF($input: CreateViewFieldInput!) { createViewField(input: $input) { id } }",
                {"input": {"viewId": vid, "fieldMetadataId": cf["id"], "isVisible": True, "position": i}}, action="Create view field",
            )
    return ConnectorResult(ok=True, data={"id": vid, "summary": f"Created {vtype.lower()} list '{view['name']}' on {obj.get('labelPlural')}{group_summary}{sort_summary}."})


async def _find_view(client, ident: str) -> dict | None:
    res = await client.query_meta("query V { getViews { id name } }", action="List views")
    if not res.ok:
        return None
    n = _norm(ident)
    for node in (res.data or {}).get("getViews") or []:
        if node.get("id") == ident or n == _norm(node.get("name") or ""):
            return node
    return None


async def update_view(client, user_id, inp) -> ConnectorResult:
    view = await _find_view(client, inp.get("view_id") or inp.get("name") or "")
    if not view:
        return ConnectorResult(ok=False, error=f"No view matching '{inp.get('view_id') or inp.get('name')}'.")
    update: dict = {}
    if inp.get("new_name"):
        update["name"] = inp["new_name"]
    if not update:
        return ConnectorResult(ok=False, error="Nothing to update (pass new_name).")
    res = await client.query_meta(
        "mutation UpdateView($id: String!, $input: UpdateViewInput!) { updateView(id: $id, input: $input) { id } }",
        {"id": view["id"], "input": update}, action="Update view",
    )
    return res if not res.ok else ConnectorResult(ok=True, data={"summary": f"Updated the '{view.get('name')}' list."})


async def delete_view(client, user_id, inp) -> ConnectorResult:
    view = await _find_view(client, inp.get("view_id") or inp.get("name") or "")
    if not view:
        return ConnectorResult(ok=False, error=f"No view matching '{inp.get('view_id') or inp.get('name')}'.")
    # deleteView takes id directly and returns Boolean (no selection set).
    res = await client.query_meta(
        "mutation DeleteView($id: String!) { deleteView(id: $id) }",
        {"id": view["id"]}, action="Delete view",
    )
    return res if not res.ok else ConnectorResult(ok=True, data={"status": "deleted", "summary": f"Deleted the '{view.get('name')}' list."})


# action name -> handler (client, user_id, inp)
METADATA_HANDLERS = {
    "list_objects": list_objects, "list_views": list_views,
    "create_field": create_field, "update_field": update_field, "delete_field": delete_field,
    "create_object": create_object, "delete_object": delete_object,
    "create_view": create_view, "update_view": update_view, "delete_view": delete_view,
}
