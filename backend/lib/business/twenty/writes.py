"""
Phase 3 — read/WRITE tools for the owned Jarvis CRM (Twenty), GUARDED.

Mutations mirror the proven Phase-1 importer shape (createOne/updateOne/deleteOne
generated CRUD, composite name/emails/phones/amount inputs, note/task target joins)
and are built DEFENSIVELY from the introspected schema — a field is only sent if the
object actually has it. Never guesses field names.

Every write is scoped to the per-user workspace by the caller (tools.execute_twenty_tool
resolves `TwentyClient.for_user(user_id)` first), so a write can only ever touch that
client's workspace — the isolation boundary from Phase 2.

Guardrails:
  - additive writes (create/update/move/note/task/tag) execute directly and return a
    clear summary of what changed;
  - DESTRUCTIVE writes (delete_person, delete_opportunity) are listed in chat.py's
    WRITE_ACTIONS, so the chat stream intercepts them and requires hold-to-confirm
    BEFORE this code runs;
  - create_person is idempotent on email (returns the existing person instead of a dup);
    add/remove_tag are set-semantics idempotent.
GHL is never written to here — writes go to Twenty only.
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import store
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import TwentySchema


def _cap(name_singular: str) -> str:
    return name_singular[:1].upper() + name_singular[1:]


def _has(schema: TwentySchema, alias: str, field_name: str) -> bool:
    obj = schema.obj(alias)
    return bool(obj and obj.field_by_name(field_name))


def _full_name(node: dict) -> str:
    n = node.get("name") or {}
    if isinstance(n, dict):
        return f"{n.get('firstName', '')} {n.get('lastName', '')}".strip()
    return str(n or "")


async def _create(client: TwentyClient, schema: TwentySchema, alias: str, data: dict) -> ConnectorResult:
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    cap = _cap(obj.name_singular)
    mutation = f"mutation Create{cap}($data: {cap}CreateInput!) {{ create{cap}(data: $data) {{ id }} }}"
    res = await client.query_data(mutation, {"data": data}, action=f"Create {alias}")
    if not res.ok:
        return res
    rec = (res.data or {}).get(f"create{cap}") or {}
    return ConnectorResult(ok=True, data={"id": rec.get("id")})


async def _update(client: TwentyClient, schema: TwentySchema, alias: str, record_id: str, data: dict) -> ConnectorResult:
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    cap = _cap(obj.name_singular)
    mutation = (
        f"mutation Update{cap}($id: UUID!, $data: {cap}UpdateInput!) "
        f"{{ update{cap}(id: $id, data: $data) {{ id }} }}"
    )
    res = await client.query_data(mutation, {"id": record_id, "data": data}, action=f"Update {alias}")
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": record_id})


async def _delete(client: TwentyClient, schema: TwentySchema, alias: str, record_id: str) -> ConnectorResult:
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    cap = _cap(obj.name_singular)
    mutation = f"mutation Delete{cap}($id: UUID!) {{ delete{cap}(id: $id) {{ id }} }}"
    res = await client.query_data(mutation, {"id": record_id}, action=f"Delete {alias}")
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": record_id})


# ── lookups ───────────────────────────────────────────────────────────────────
async def _find_person(client: TwentyClient, schema: TwentySchema, query: str) -> dict | None:
    """Find a person by name or email (client-side match, version-safe)."""
    plural = schema.obj("person").name_plural
    q = (query or "").strip().lower()
    if not q:
        return None
    res = await client.query_data(
        f"query P {{ {plural}(first: 200) {{ edges {{ node {{ id name {{ firstName lastName }} "
        f"emails {{ primaryEmail }} }} }} }} }}",
        action="Find person",
    )
    if not res.ok:
        return None
    for edge in ((res.data or {}).get(plural) or {}).get("edges") or []:
        node = edge.get("node") or {}
        email = ((node.get("emails") or {}).get("primaryEmail") or "").lower()
        if q in _full_name(node).lower() or (q and q in email):
            return node
    return None


async def _find_opportunity(client: TwentyClient, schema: TwentySchema, query: str) -> dict | None:
    obj = schema.obj("opportunity")
    if not obj:
        return None
    plural = obj.name_plural
    q = (query or "").strip().lower()
    res = await client.query_data(
        f"query O {{ {plural}(first: 200) {{ edges {{ node {{ id name }} }} }} }}",
        action="Find opportunity",
    )
    if not res.ok:
        return None
    for edge in ((res.data or {}).get(plural) or {}).get("edges") or []:
        node = edge.get("node") or {}
        if q in (node.get("name") or "").lower():
            return node
    return None


async def _resolve_id(client, schema, alias, inp, id_key) -> tuple[str | None, str]:
    """Resolve a record id from an explicit id or a `query` string. Returns (id, label)."""
    rid = inp.get(id_key)
    if rid:
        return rid, rid
    query = inp.get("query") or inp.get("name")
    finder = _find_person if alias == "person" else _find_opportunity
    node = await finder(client, schema, query)
    if not node:
        return None, query or ""
    label = _full_name(node) if alias == "person" else (node.get("name") or "")
    return node.get("id"), label


async def _stage_targets(user_id: str) -> dict[str, list[tuple[str, str]]]:
    """label(lower) -> [(field_name, option_value)] from the structure map."""
    out: dict[str, list[tuple[str, str]]] = {}
    for (kind, _), row in (await store.load_structure_map(user_id)).items():
        if kind != "stage":
            continue
        extra = row.get("extra") or {}
        label = (extra.get("label") or "").strip().lower()
        if label and extra.get("field_name"):
            out.setdefault(label, []).append((extra["field_name"], row["twenty_id"]))
    return out


def _tag_field(schema: TwentySchema) -> str | None:
    """The multi-select field holding tags (importer mirrors GHL tags into `ghlTags`)."""
    for cand in ("ghlTags", "tags"):
        if _has(schema, "person", cand):
            return cand
    return None


# ── input builders (defensive) ─────────────────────────────────────────────────
def _person_input(schema: TwentySchema, inp: dict) -> dict:
    data: dict = {}
    first, last = inp.get("first_name"), inp.get("last_name")
    if (first is not None or last is not None) and _has(schema, "person", "name"):
        data["name"] = {"firstName": first or "", "lastName": last or ""}
    if inp.get("email") and _has(schema, "person", "emails"):
        data["emails"] = {"primaryEmail": inp["email"], "additionalEmails": []}
    if inp.get("phone") and _has(schema, "person", "phones"):
        data["phones"] = {"primaryPhoneNumber": inp["phone"], "primaryPhoneCountryCode": "", "primaryPhoneCallingCode": ""}
    if inp.get("city") and _has(schema, "person", "city"):
        data["city"] = inp["city"]
    if inp.get("job_title") and _has(schema, "person", "jobTitle"):
        data["jobTitle"] = inp["job_title"]
    return data


# ── public write actions ────────────────────────────────────────────────────────
async def create_person(client, schema, user_id, inp) -> ConnectorResult:
    # Idempotent on email: return the existing person rather than duplicating.
    if inp.get("email"):
        existing = await _find_person(client, schema, inp["email"])
        if existing:
            return ConnectorResult(ok=True, data={
                "id": existing.get("id"), "name": _full_name(existing),
                "created": False, "summary": f"{_full_name(existing)} already exists — no duplicate created.",
            })
    data = _person_input(schema, inp)
    if not data:
        return ConnectorResult(ok=False, error="Provide at least a name or email for the contact.")
    res = await _create(client, schema, "person", data)
    if not res.ok:
        return res
    name = f"{inp.get('first_name', '')} {inp.get('last_name', '')}".strip() or inp.get("email", "contact")
    return ConnectorResult(ok=True, data={"id": res.data["id"], "name": name, "created": True,
                                          "summary": f"Created contact {name}."})


async def update_person(client, schema, user_id, inp) -> ConnectorResult:
    pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
    if not pid:
        return ConnectorResult(ok=False, error=f"No contact matching '{label}'.")
    data = _person_input(schema, inp)
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "person", pid, data)
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": pid, "summary": f"Updated {label or 'contact'} ({', '.join(data.keys())})."})


async def create_opportunity(client, schema, user_id, inp) -> ConnectorResult:
    if not schema.obj("opportunity"):
        return ConnectorResult(ok=False, error="This CRM has no Opportunity object.")
    data: dict = {}
    if _has(schema, "opportunity", "name"):
        data["name"] = inp.get("name") or "Opportunity"
    if inp.get("amount") is not None and _has(schema, "opportunity", "amount"):
        try:
            data["amount"] = {"amountMicros": int(float(inp["amount"]) * 1_000_000),
                              "currencyCode": (inp.get("currency") or "USD").upper()}
        except (TypeError, ValueError):
            pass
    # stage
    stage_summary = ""
    if inp.get("stage"):
        targets = await _stage_targets(user_id)
        pairs = targets.get(inp["stage"].strip().lower())
        if not pairs:
            known = ", ".join(sorted(targets)) or "none (run the import first)"
            return ConnectorResult(ok=False, error=f"No stage '{inp['stage']}'. Known stages: {known}.")
        fn, val = pairs[0]
        if _has(schema, "opportunity", fn):
            data[fn] = val
            stage_summary = f" at stage {inp['stage']}"
    # point of contact
    if (inp.get("person_query") or inp.get("person_id")) and _has(schema, "opportunity", "pointOfContact"):
        person = await _find_person(client, schema, inp.get("person_query")) if inp.get("person_query") else None
        person_id = inp.get("person_id") or (person.get("id") if person else None)
        if person_id:
            data["pointOfContactId"] = person_id
    res = await _create(client, schema, "opportunity", data)
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": res.data["id"], "name": data.get("name"),
                                          "summary": f"Created opportunity '{data.get('name')}'{stage_summary}."})


async def update_opportunity(client, schema, user_id, inp) -> ConnectorResult:
    oid, label = await _resolve_id(client, schema, "opportunity", inp, "opportunity_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No opportunity matching '{label}'.")
    data: dict = {}
    if inp.get("name") and _has(schema, "opportunity", "name"):
        data["name"] = inp["name"]
    if inp.get("amount") is not None and _has(schema, "opportunity", "amount"):
        try:
            data["amount"] = {"amountMicros": int(float(inp["amount"]) * 1_000_000),
                              "currencyCode": (inp.get("currency") or "USD").upper()}
        except (TypeError, ValueError):
            pass
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "opportunity", oid, data)
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": oid, "summary": f"Updated opportunity '{label}' ({', '.join(data.keys())})."})


async def move_opportunity_stage(client, schema, user_id, inp) -> ConnectorResult:
    oid, label = await _resolve_id(client, schema, "opportunity", inp, "opportunity_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No opportunity matching '{label}'.")
    targets = await _stage_targets(user_id)
    pairs = targets.get((inp.get("stage") or "").strip().lower())
    if not pairs:
        known = ", ".join(sorted(targets)) or "none (run the import first)"
        return ConnectorResult(ok=False, error=f"No stage '{inp.get('stage')}'. Known stages: {known}.")
    fn, val = pairs[0]
    if not _has(schema, "opportunity", fn):
        return ConnectorResult(ok=False, error=f"This CRM's Opportunity has no '{fn}' stage field.")
    res = await _update(client, schema, "opportunity", oid, {fn: val})
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": oid, "summary": f"Moved '{label}' to stage {inp['stage']}."})


async def _attach_target(client, schema, target_alias: str, parent_id: str, person_id: str):
    obj = schema.obj(target_alias)
    if not obj:
        return
    cap = _cap(obj.name_singular)
    key = target_alias.replace("Target", "")  # note / task
    mutation = f"mutation Create{cap}($data: {cap}CreateInput!) {{ create{cap}(data: $data) {{ id }} }}"
    await client.query_data(mutation, {"data": {f"{key}Id": parent_id, "personId": person_id}}, action=f"Attach {target_alias}")


async def add_note(client, schema, user_id, inp) -> ConnectorResult:
    pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
    if not pid:
        return ConnectorResult(ok=False, error=f"No contact matching '{label}' to attach the note to.")
    body = inp.get("body") or inp.get("note") or ""
    if not body:
        return ConnectorResult(ok=False, error="The note body is empty.")
    data: dict = {}
    if _has(schema, "note", "title"):
        data["title"] = inp.get("title") or body[:60]
    if _has(schema, "note", "body"):
        data["body"] = body
    res = await _create(client, schema, "note", data)
    if not res.ok:
        return res
    await _attach_target(client, schema, "noteTarget", res.data["id"], pid)
    return ConnectorResult(ok=True, data={"id": res.data["id"], "summary": f"Added a note to {label}."})


async def add_task(client, schema, user_id, inp) -> ConnectorResult:
    title = inp.get("title")
    if not title:
        return ConnectorResult(ok=False, error="A task needs a title.")
    data: dict = {}
    if _has(schema, "task", "title"):
        data["title"] = title
    if inp.get("body") and _has(schema, "task", "body"):
        data["body"] = inp["body"]
    if inp.get("due_at") and _has(schema, "task", "dueAt"):
        data["dueAt"] = inp["due_at"]
    res = await _create(client, schema, "task", data)
    if not res.ok:
        return res
    summary = f"Created task '{title}'."
    if inp.get("person_query") or inp.get("person_id"):
        pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
        if pid:
            await _attach_target(client, schema, "taskTarget", res.data["id"], pid)
            summary = f"Created task '{title}' for {label}."
    return ConnectorResult(ok=True, data={"id": res.data["id"], "summary": summary})


async def complete_task(client, schema, user_id, inp) -> ConnectorResult:
    # Tasks aren't searchable by the person finder — require an explicit id.
    tid = inp.get("task_id")
    if not tid:
        return ConnectorResult(ok=False, error="Provide the task_id to complete (list tasks first).")
    if not _has(schema, "task", "status"):
        return ConnectorResult(ok=False, error="This CRM's Task has no status field.")
    res = await _update(client, schema, "task", tid, {"status": "DONE"})
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": tid, "summary": "Marked the task complete.", "idempotent": True})


async def _set_tags(client, schema, user_id, inp, *, add: bool) -> ConnectorResult:
    field = _tag_field(schema)
    if not field:
        return ConnectorResult(ok=False, error="This CRM has no tags field on Person.")
    pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
    if not pid:
        return ConnectorResult(ok=False, error=f"No contact matching '{label}'.")
    tag = (inp.get("tag") or "").strip()
    if not tag:
        return ConnectorResult(ok=False, error="No tag provided.")
    # Read current tags, then set-union/diff (idempotent).
    plural = schema.obj("person").name_plural
    res = await client.query_data(
        f"query T {{ {plural}(first: 1, filter: {{ id: {{ eq: \"{pid}\" }} }}) {{ edges {{ node {{ {field} }} }} }} }}",
        action="Read tags",
    )
    current = []
    if res.ok:
        edges = ((res.data or {}).get(plural) or {}).get("edges") or []
        if edges:
            current = (edges[0].get("node") or {}).get(field) or []
    current = [t for t in (current or []) if t]
    if add:
        if tag in current:
            return ConnectorResult(ok=True, data={"id": pid, "summary": f"{label} already has tag '{tag}'.", "idempotent": True})
        new_tags = current + [tag]
    else:
        if tag not in current:
            return ConnectorResult(ok=True, data={"id": pid, "summary": f"{label} doesn't have tag '{tag}'.", "idempotent": True})
        new_tags = [t for t in current if t != tag]
    upd = await _update(client, schema, "person", pid, {field: new_tags})
    if not upd.ok:
        return upd
    verb = "Added" if add else "Removed"
    return ConnectorResult(ok=True, data={"id": pid, "summary": f"{verb} tag '{tag}' {'to' if add else 'from'} {label}."})


async def add_tag(client, schema, user_id, inp) -> ConnectorResult:
    return await _set_tags(client, schema, user_id, inp, add=True)


async def remove_tag(client, schema, user_id, inp) -> ConnectorResult:
    return await _set_tags(client, schema, user_id, inp, add=False)


async def delete_person(client, schema, user_id, inp) -> ConnectorResult:
    pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
    if not pid:
        return ConnectorResult(ok=False, error=f"No contact matching '{label}'.")
    res = await _delete(client, schema, "person", pid)
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": pid, "status": "deleted", "summary": f"Deleted contact {label}."})


async def delete_opportunity(client, schema, user_id, inp) -> ConnectorResult:
    oid, label = await _resolve_id(client, schema, "opportunity", inp, "opportunity_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No opportunity matching '{label}'.")
    res = await _delete(client, schema, "opportunity", oid)
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": oid, "status": "deleted", "summary": f"Deleted opportunity '{label}'."})


# action name -> handler
WRITE_HANDLERS = {
    "create_person": create_person,
    "update_person": update_person,
    "create_opportunity": create_opportunity,
    "update_opportunity": update_opportunity,
    "move_opportunity_stage": move_opportunity_stage,
    "add_note": add_note,
    "add_task": add_task,
    "complete_task": complete_task,
    "add_tag": add_tag,
    "remove_tag": remove_tag,
    "delete_person": delete_person,
    "delete_opportunity": delete_opportunity,
}
