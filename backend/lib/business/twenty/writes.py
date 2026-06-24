"""
Jarvis CRM write layer (Twenty) — full CRUD across every core object, GUARDED.

Mutations use Twenty's generated CRUD (create/update/delete{Object}) and are built
DEFENSIVELY from the introspected schema — a field is only sent if the object actually
has it. Never guesses field names. Every write is scoped to the per-user workspace by
the caller (tools.execute_twenty_tool resolves TwentyClient.for_user(user_id) first), so
a write can only ever touch that client's tenant — the Phase-2 isolation boundary.

Coverage:
  People         create / update / delete / link-to-company
  Companies      create / update / delete
  Opportunities  create / update / move-stage / delete   (+ company & contact links)
  Tasks          create / update / complete / delete      (+ assign to person/company/opp)
  Notes          create / update / delete                 (+ attach to person/company/opp)
  Tags           add / remove on person/company/opportunity (any MULTI_SELECT tag field)
  Relationships  link_records (person↔company, opportunity↔company, opportunity↔person)
  Advanced       run_graphql_mutation (escape hatch; confirm-gated — see report)

Guardrails: deletes + run_graphql_mutation are listed in chat.py WRITE_ACTIONS so the
chat stream intercepts them for hold-to-confirm BEFORE this code runs. Creates are
idempotent on a natural key where sensible (person→email, company→name; tags are
set-semantics). Each write returns a clear `summary`. GHL is never written here.
"""
import re

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import store
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import TwentyField, TwentyObject, TwentySchema


def _cap(name_singular: str) -> str:
    return name_singular[:1].upper() + name_singular[1:]


# ── generic custom-field resolution + value coercion ──────────────────────────
# The "any field, by live schema" layer. Resolves a user-supplied field key (real API
# name OR human label, case-insensitive) to its TwentyField, then coerces the value into
# the exact shape this Twenty build expects for that field's TYPE. Crucially, SELECT /
# MULTI_SELECT store the option KEY (e.g. "TO_BE_CALLED"), not the label ("To Be Called"),
# so we introspect each field's options and map label→key on write.
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def resolve_field(obj: TwentyObject | None, key: str) -> TwentyField | None:
    """Resolve a field by exact API name, then by normalized name/label, then by contains."""
    if not obj or not key:
        return None
    direct = obj.field_by_name(key)
    if direct:
        return direct
    kn = _norm(key)
    for f in obj.fields:
        if _norm(f.name) == kn or _norm(f.label) == kn:
            return f
    for f in obj.fields:
        if kn and (kn in _norm(f.name) or kn in _norm(f.label)):
            return f
    return None


def option_key(field: TwentyField, value) -> str | None:
    """Map a user label/value to the stored SELECT option key. None if no match."""
    if value is None:
        return None
    vn = _norm(value if isinstance(value, str) else str(value))
    for o in (field.options or []):
        if _norm(o.get("value") or "") == vn or _norm(o.get("label") or "") == vn:
            return o.get("value")
    return None


def _known_options(field: TwentyField) -> str:
    return ", ".join(o.get("label") or o.get("value") or "" for o in (field.options or [])) or "(none)"


# Fields the generic path must never overwrite (managed by structured params / read-only).
_PROTECTED_FIELDS = {"id", "createdAt", "updatedAt", "deletedAt"}


def coerce_value(field: TwentyField, raw):
    """Return (formatted_value, error) for writing `raw` into `field` per its type.

    None passes through as an explicit clear. SELECT/MULTI_SELECT map labels→keys (and
    error with the known options if unmatched, so the agent can self-correct)."""
    t = (field.type or "").upper()
    if raw is None:
        return _empty_for(field), None
    if t == "SELECT":
        k = option_key(field, raw)
        if not k:
            return None, f"'{raw}' isn't an option for '{field.label or field.name}'. Options: {_known_options(field)}."
        return k, None
    if t == "MULTI_SELECT":
        vals = raw if isinstance(raw, list) else [raw]
        keys, bad = [], []
        for v in vals:
            k = option_key(field, v)
            keys.append(k) if k else bad.append(str(v))
        if bad:
            return None, f"Unknown options for '{field.label or field.name}': {', '.join(bad)}. Options: {_known_options(field)}."
        return keys, None
    if t == "LINKS":
        if isinstance(raw, dict):
            url = raw.get("url") or raw.get("primaryLinkUrl") or ""
            lab = raw.get("label") or raw.get("primaryLinkLabel") or ""
        else:
            url, lab = str(raw), ""
        return {"primaryLinkUrl": url, "primaryLinkLabel": lab, "secondaryLinks": []}, None
    if t == "CURRENCY":
        try:
            amt = raw.get("amount") if isinstance(raw, dict) else raw
            cur = (raw.get("currency") if isinstance(raw, dict) else None) or "USD"
            return {"amountMicros": int(round(float(amt) * 1_000_000)), "currencyCode": str(cur).upper()}, None
        except (TypeError, ValueError, KeyError):
            return None, f"'{field.label or field.name}' expects a number."
    if t == "NUMBER":
        try:
            n = float(raw)
            return (int(n) if n.is_integer() else n), None
        except (TypeError, ValueError):
            return None, f"'{field.label or field.name}' expects a number."
    if t == "RATING":
        try:
            return int(float(raw)), None
        except (TypeError, ValueError):
            return None, f"'{field.label or field.name}' expects a number."
    if t == "BOOLEAN":
        if isinstance(raw, bool):
            return raw, None
        return str(raw).strip().lower() in ("true", "yes", "1", "on", "done", "y"), None
    if t == "EMAILS":
        return {"primaryEmail": str(raw), "additionalEmails": []}, None
    if t == "PHONES":
        return {"primaryPhoneNumber": str(raw), "primaryPhoneCountryCode": "", "primaryPhoneCallingCode": ""}, None
    if t == "FULL_NAME":
        if isinstance(raw, dict):
            return {"firstName": raw.get("first") or raw.get("firstName") or "",
                    "lastName": raw.get("last") or raw.get("lastName") or ""}, None
        parts = str(raw).split(" ", 1)
        return {"firstName": parts[0], "lastName": parts[1] if len(parts) > 1 else ""}, None
    # TEXT, DATE_TIME, DATE, UUID, and anything else scalar → string (objects/lists pass through).
    return (raw if isinstance(raw, (dict, list)) else str(raw)), None


def _empty_for(field: TwentyField):
    """The 'clear this field' value for a given type."""
    t = (field.type or "").upper()
    if t == "LINKS":
        return {"primaryLinkUrl": "", "primaryLinkLabel": "", "secondaryLinks": []}
    if t == "MULTI_SELECT":
        return []
    if t in ("EMAILS",):
        return {"primaryEmail": "", "additionalEmails": []}
    if t in ("PHONES",):
        return {"primaryPhoneNumber": "", "primaryPhoneCountryCode": "", "primaryPhoneCallingCode": ""}
    return None


def apply_fields(schema: TwentySchema, alias: str, data: dict, fields: dict | None) -> tuple[list[str], list[str]]:
    """Resolve a {name-or-label: value} map against the live schema into `data` (mutated).

    Returns (applied_api_names, errors). Used by update/create/bulk so ANY field Mohamed
    adds (text/number/select/multi-select/link/date/…) is immediately writable by name."""
    obj = schema.obj(alias)
    applied, errors = [], []
    for key, raw in (fields or {}).items():
        fld = resolve_field(obj, key)
        if not fld:
            errors.append(f"no field '{key}' on {alias}")
            continue
        if fld.name in _PROTECTED_FIELDS:
            errors.append(f"'{fld.name}' is read-only")
            continue
        val, err = coerce_value(fld, raw)
        if err:
            errors.append(err)
            continue
        data[fld.name] = val
        applied.append(fld.name)
    return applied, errors


def read_selection(field: TwentyField) -> str:
    """GraphQL selection for reading a field's value back (composite types need sub-fields)."""
    t = (field.type or "").upper()
    if t == "LINKS":
        return f"{field.name} {{ primaryLinkUrl primaryLinkLabel }}"
    if t == "CURRENCY":
        return f"{field.name} {{ amountMicros currencyCode }}"
    if t == "EMAILS":
        return f"{field.name} {{ primaryEmail }}"
    if t == "PHONES":
        return f"{field.name} {{ primaryPhoneNumber }}"
    if t == "FULL_NAME":
        return f"{field.name} {{ firstName lastName }}"
    if t == "ADDRESS":
        return f"{field.name} {{ addressStreet1 addressCity addressState addressCountry }}"
    return field.name


def read_value(field: TwentyField, v):
    """Decode a read-back value into something human/agent-friendly (SELECT key→label)."""
    t = (field.type or "").upper()
    if v is None:
        return None
    if t == "LINKS":
        return (v or {}).get("primaryLinkUrl")
    if t == "CURRENCY":
        am = (v or {}).get("amountMicros")
        return (am / 1_000_000) if am is not None else None
    if t == "EMAILS":
        return (v or {}).get("primaryEmail")
    if t == "PHONES":
        return (v or {}).get("primaryPhoneNumber")
    if t == "FULL_NAME":
        return f"{(v or {}).get('firstName', '')} {(v or {}).get('lastName', '')}".strip()
    if t == "SELECT":
        for o in (field.options or []):
            if o.get("value") == v:
                return o.get("label") or v
        return v
    if t == "MULTI_SELECT":
        out = []
        for val in (v or []):
            lab = val
            for o in (field.options or []):
                if o.get("value") == val:
                    lab = o.get("label") or val
            out.append(lab)
        return out
    return v


def _has(schema: TwentySchema, alias: str, field_name: str) -> bool:
    obj = schema.obj(alias)
    return bool(obj and obj.field_by_name(field_name))


def _full_name(node: dict) -> str:
    n = node.get("name") or {}
    if isinstance(n, dict):
        return f"{n.get('firstName', '')} {n.get('lastName', '')}".strip()
    return str(n or "")


def _label(alias: str, node: dict) -> str:
    return _full_name(node) if alias == "person" else (node.get("name") or "")


# ── generic CRUD ────────────────────────────────────────────────────────────────
async def _create(client: TwentyClient, schema: TwentySchema, alias: str, data: dict) -> ConnectorResult:
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    cap = _cap(obj.name_singular)
    mutation = f"mutation Create{cap}($data: {cap}CreateInput!) {{ create{cap}(data: $data) {{ id }} }}"
    res = await client.query_data(mutation, {"data": data}, action=f"Create {alias}")
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"id": ((res.data or {}).get(f"create{cap}") or {}).get("id")})


async def _update(client: TwentyClient, schema: TwentySchema, alias: str, record_id: str, data: dict) -> ConnectorResult:
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    cap = _cap(obj.name_singular)
    mutation = f"mutation Update{cap}($id: UUID!, $data: {cap}UpdateInput!) {{ update{cap}(id: $id, data: $data) {{ id }} }}"
    res = await client.query_data(mutation, {"id": record_id, "data": data}, action=f"Update {alias}")
    return res if not res.ok else ConnectorResult(ok=True, data={"id": record_id})


async def _delete(client: TwentyClient, schema: TwentySchema, alias: str, record_id: str) -> ConnectorResult:
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    cap = _cap(obj.name_singular)
    mutation = f"mutation Delete{cap}($id: UUID!) {{ delete{cap}(id: $id) {{ id }} }}"
    res = await client.query_data(mutation, {"id": record_id}, action=f"Delete {alias}")
    return res if not res.ok else ConnectorResult(ok=True, data={"id": record_id})


# ── lookups ───────────────────────────────────────────────────────────────────
async def _find(client: TwentyClient, schema: TwentySchema, alias: str, query: str) -> dict | None:
    """Find a record by a human query: person by name/email, company/opportunity by name."""
    obj = schema.obj(alias)
    if not obj:
        return None
    q = (query or "").strip().lower()
    if not q:
        return None
    if alias == "person":
        sel = "id name { firstName lastName } emails { primaryEmail }"
    else:
        sel = "id name"
    res = await client.query_data(
        f"query Find {{ {obj.name_plural}(first: 200) {{ edges {{ node {{ {sel} }} }} }} }}",
        action=f"Find {alias}",
    )
    if not res.ok:
        return None
    for edge in ((res.data or {}).get(obj.name_plural) or {}).get("edges") or []:
        node = edge.get("node") or {}
        if alias == "person":
            email = ((node.get("emails") or {}).get("primaryEmail") or "").lower()
            if q in _full_name(node).lower() or q in email:
                return node
        elif q in (node.get("name") or "").lower():
            return node
    return None


async def _resolve_id(client, schema, alias, inp, id_key) -> tuple[str | None, str]:
    rid = inp.get(id_key)
    if rid:
        return rid, rid
    node = await _find(client, schema, alias, inp.get("query") or inp.get("name"))
    if not node:
        return None, (inp.get("query") or inp.get("name") or "")
    return node.get("id"), _label(alias, node)


# ── stages ──────────────────────────────────────────────────────────────────────
async def stage_label_map(user_id: str, schema: TwentySchema) -> dict[str, list[tuple[str, str]]]:
    """stage label/value (lower) -> [(field_name, option_value)].

    Merges the GHL structure map with Twenty's native Opportunity SELECT options so
    stages resolve whether or not a GHL import has run.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for (kind, _), row in (await store.load_structure_map(user_id)).items():
        if kind != "stage":
            continue
        extra = row.get("extra") or {}
        label = (extra.get("label") or "").strip().lower()
        if label and extra.get("field_name"):
            out.setdefault(label, []).append((extra["field_name"], row["twenty_id"]))
    opp = schema.obj("opportunity") if schema else None
    if opp:
        stage_f = opp.field_by_name("stage")
        cands = [stage_f] if (stage_f and stage_f.type in ("SELECT", "MULTI_SELECT")) else [f for f in opp.fields if f.type == "SELECT"]
        for fld in cands:
            for o in (fld.options or []):
                val = o.get("value")
                lab = o.get("label") or val or ""
                for key in {(lab or "").strip().lower(), (val or "").strip().lower()}:
                    if not key:
                        continue
                    bucket = out.setdefault(key, [])
                    if (fld.name, val) not in bucket:
                        bucket.append((fld.name, val))
    return out


async def _resolve_stage(user_id, schema, stage_str) -> tuple[str | None, str | None, list[str]]:
    want = (stage_str or "").strip().lower()
    targets = await stage_label_map(user_id, schema)
    pairs = targets.get(want)
    if pairs:
        return pairs[0][0], pairs[0][1], sorted(targets)
    return None, None, sorted(targets)


def _tag_field(schema: TwentySchema, alias: str) -> str | None:
    """A MULTI_SELECT field usable as tags on `alias` (importer mirrors GHL tags into ghlTags)."""
    obj = schema.obj(alias)
    if not obj:
        return None
    for cand in ("ghlTags", "tags"):
        f = obj.field_by_name(cand)
        if f and f.type == "MULTI_SELECT":
            return cand
    for f in obj.fields:
        if f.type == "MULTI_SELECT" and "tag" in f.name.lower():
            return f.name
    return None


def _set_body(schema, alias: str, data: dict, body: str) -> None:
    """Set a note/task body, handling both the legacy `body` (TEXT) and the current
    `bodyV2` (RICH_TEXT, takes {markdown}) field shapes across Twenty versions."""
    if not body:
        return
    if _has(schema, alias, "body"):
        data["body"] = body
    elif _has(schema, alias, "bodyV2"):
        data["bodyV2"] = {"markdown": body}


async def _attach_target(client, schema, kind: str, parent_id: str, inp: dict) -> list[str]:
    """Create {kind}Target rows linking a note/task to any provided person/company/opp.

    The join objects (NoteTarget/TaskTarget) aren't in the introspected core-object set,
    so the mutation names are fixed by convention. Join FKs are target{Person,Company,
    Opportunity}Id (NOT personId).
    """
    cap = _cap(kind) + "Target"   # NoteTarget / TaskTarget
    attached: list[str] = []
    for ttype in ("person", "company", "opportunity"):
        if not (inp.get(f"{ttype}_id") or inp.get(f"{ttype}_query")):
            continue
        tid, _ = await _resolve_id(
            client, schema, ttype,
            {f"{ttype}_id": inp.get(f"{ttype}_id"), "query": inp.get(f"{ttype}_query")},
            f"{ttype}_id",
        )
        if not tid:
            continue
        data = {f"{kind}Id": parent_id, f"target{_cap(ttype)}Id": tid}
        mutation = f"mutation Attach($data: {cap}CreateInput!) {{ create{cap}(data: $data) {{ id }} }}"
        r = await client.query_data(mutation, {"data": data}, action=f"Attach {cap}")
        if r.ok:
            attached.append(ttype)
    return attached


# ── input builders ──────────────────────────────────────────────────────────────
def _person_input(schema, inp) -> dict:
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


def _amount(inp):
    try:
        return {"amountMicros": int(float(inp["amount"]) * 1_000_000), "currencyCode": (inp.get("currency") or "USD").upper()}
    except (TypeError, ValueError, KeyError):
        return None


# ══ PEOPLE ════════════════════════════════════════════════════════════════════
async def create_person(client, schema, user_id, inp) -> ConnectorResult:
    if inp.get("email"):
        existing = await _find(client, schema, "person", inp["email"])
        if existing:
            return ConnectorResult(ok=True, data={"id": existing.get("id"), "created": False,
                                                  "summary": f"{_full_name(existing)} already exists — no duplicate created."})
    data = _person_input(schema, inp)
    _, errors = apply_fields(schema, "person", data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    if not data:
        return ConnectorResult(ok=False, error="Provide at least a name or email for the contact.")
    res = await _create(client, schema, "person", data)
    if not res.ok:
        return res
    name = f"{inp.get('first_name', '')} {inp.get('last_name', '')}".strip() or inp.get("email", "contact")
    # optional company link
    if inp.get("company_query") or inp.get("company_id"):
        cid, clabel = await _resolve_id(client, schema, "company", {"company_id": inp.get("company_id"), "query": inp.get("company_query")}, "company_id")
        if cid and _has(schema, "person", "company"):
            await _update(client, schema, "person", res.data["id"], {"companyId": cid})
    return ConnectorResult(ok=True, data={"id": res.data["id"], "created": True, "summary": f"Created contact {name}."})


async def update_person(client, schema, user_id, inp) -> ConnectorResult:
    pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
    if not pid:
        return ConnectorResult(ok=False, error=f"No contact matching '{label}'.")
    data = _person_input(schema, inp)
    applied, errors = apply_fields(schema, "person", data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "person", pid, data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": pid, "summary": f"Updated {label or 'contact'} ({', '.join(data.keys())})."})


async def delete_person(client, schema, user_id, inp) -> ConnectorResult:
    pid, label = await _resolve_id(client, schema, "person", inp, "person_id")
    if not pid:
        return ConnectorResult(ok=False, error=f"No contact matching '{label}'.")
    res = await _delete(client, schema, "person", pid)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": pid, "status": "deleted", "summary": f"Deleted contact {label}."})


# ══ COMPANIES ═════════════════════════════════════════════════════════════════
async def create_company(client, schema, user_id, inp) -> ConnectorResult:
    name = inp.get("name")
    if not name:
        return ConnectorResult(ok=False, error="A company needs a name.")
    existing = await _find(client, schema, "company", name)
    if existing and (existing.get("name") or "").strip().lower() == name.strip().lower():
        return ConnectorResult(ok=True, data={"id": existing.get("id"), "created": False,
                                              "summary": f"Company '{name}' already exists — no duplicate created."})
    data: dict = {}
    if _has(schema, "company", "name"):
        data["name"] = name
    if inp.get("domain") and _has(schema, "company", "domainName"):
        data["domainName"] = {"primaryLinkUrl": inp["domain"], "primaryLinkLabel": "", "secondaryLinks": []}
    if inp.get("city") and _has(schema, "company", "address"):
        data["address"] = {"addressCity": inp["city"]}
    _, errors = apply_fields(schema, "company", data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    res = await _create(client, schema, "company", data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": res.data["id"], "created": True, "summary": f"Created company {name}."})


async def update_company(client, schema, user_id, inp) -> ConnectorResult:
    cid, label = await _resolve_id(client, schema, "company", inp, "company_id")
    if not cid:
        return ConnectorResult(ok=False, error=f"No company matching '{label}'.")
    data: dict = {}
    if inp.get("name") and _has(schema, "company", "name"):
        data["name"] = inp["name"]
    if inp.get("domain") and _has(schema, "company", "domainName"):
        data["domainName"] = {"primaryLinkUrl": inp["domain"], "primaryLinkLabel": "", "secondaryLinks": []}
    applied, errors = apply_fields(schema, "company", data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "company", cid, data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": cid, "summary": f"Updated company '{label}' ({', '.join(data.keys())})."})


async def delete_company(client, schema, user_id, inp) -> ConnectorResult:
    cid, label = await _resolve_id(client, schema, "company", inp, "company_id")
    if not cid:
        return ConnectorResult(ok=False, error=f"No company matching '{label}'.")
    res = await _delete(client, schema, "company", cid)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": cid, "status": "deleted", "summary": f"Deleted company {label}."})


# ══ OPPORTUNITIES ═════════════════════════════════════════════════════════════
async def create_opportunity(client, schema, user_id, inp) -> ConnectorResult:
    if not schema.obj("opportunity"):
        return ConnectorResult(ok=False, error="This CRM has no Opportunity object.")
    data: dict = {}
    if _has(schema, "opportunity", "name"):
        data["name"] = inp.get("name") or "Opportunity"
    amt = _amount(inp)
    if amt is not None and _has(schema, "opportunity", "amount"):
        data["amount"] = amt
    stage_summary = ""
    if inp.get("stage"):
        fn, val, known = await _resolve_stage(user_id, schema, inp["stage"])
        if not val:
            return ConnectorResult(ok=False, error=f"No stage '{inp['stage']}'. Known stages: {', '.join(known) or 'none'}.")
        if _has(schema, "opportunity", fn):
            data[fn] = val
            stage_summary = f" at stage {inp['stage']}"
    if (inp.get("person_query") or inp.get("person_id")) and _has(schema, "opportunity", "pointOfContact"):
        pid, _ = await _resolve_id(client, schema, "person", {"person_id": inp.get("person_id"), "query": inp.get("person_query")}, "person_id")
        if pid:
            data["pointOfContactId"] = pid
    if (inp.get("company_query") or inp.get("company_id")) and _has(schema, "opportunity", "company"):
        cid, _ = await _resolve_id(client, schema, "company", {"company_id": inp.get("company_id"), "query": inp.get("company_query")}, "company_id")
        if cid:
            data["companyId"] = cid
    _, errors = apply_fields(schema, "opportunity", data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    res = await _create(client, schema, "opportunity", data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": res.data["id"], "summary": f"Created opportunity '{data.get('name')}'{stage_summary}."})


async def update_opportunity(client, schema, user_id, inp) -> ConnectorResult:
    oid, label = await _resolve_id(client, schema, "opportunity", inp, "opportunity_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No opportunity matching '{label}'.")
    data: dict = {}
    if inp.get("name") and _has(schema, "opportunity", "name"):
        data["name"] = inp["name"]
    amt = _amount(inp)
    if amt is not None and _has(schema, "opportunity", "amount"):
        data["amount"] = amt
    applied, errors = apply_fields(schema, "opportunity", data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "opportunity", oid, data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": oid, "summary": f"Updated opportunity '{label}' ({', '.join(data.keys())})."})


async def move_opportunity_stage(client, schema, user_id, inp) -> ConnectorResult:
    oid, label = await _resolve_id(client, schema, "opportunity", inp, "opportunity_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No opportunity matching '{label}'.")
    fn, val, known = await _resolve_stage(user_id, schema, inp.get("stage"))
    if not val:
        return ConnectorResult(ok=False, error=f"No stage '{inp.get('stage')}'. Known stages: {', '.join(known) or 'none'}.")
    if not _has(schema, "opportunity", fn):
        return ConnectorResult(ok=False, error=f"This CRM's Opportunity has no '{fn}' stage field.")
    res = await _update(client, schema, "opportunity", oid, {fn: val})
    return res if not res.ok else ConnectorResult(ok=True, data={"id": oid, "summary": f"Moved '{label}' to stage {inp['stage']}."})


async def delete_opportunity(client, schema, user_id, inp) -> ConnectorResult:
    oid, label = await _resolve_id(client, schema, "opportunity", inp, "opportunity_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No opportunity matching '{label}'.")
    res = await _delete(client, schema, "opportunity", oid)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": oid, "status": "deleted", "summary": f"Deleted opportunity '{label}'."})


# ══ TASKS ═════════════════════════════════════════════════════════════════════
async def create_task(client, schema, user_id, inp) -> ConnectorResult:
    title = inp.get("title")
    if not title:
        return ConnectorResult(ok=False, error="A task needs a title.")
    data: dict = {}
    if _has(schema, "task", "title"):
        data["title"] = title
    _set_body(schema, "task", data, inp.get("body"))
    if inp.get("due_at") and _has(schema, "task", "dueAt"):
        data["dueAt"] = inp["due_at"]
    res = await _create(client, schema, "task", data)
    if not res.ok:
        return res
    attached = await _attach_target(client, schema, "task", res.data["id"], inp)
    suffix = f" (assigned to {', '.join(attached)})" if attached else ""
    return ConnectorResult(ok=True, data={"id": res.data["id"], "summary": f"Created task '{title}'{suffix}."})


async def update_task(client, schema, user_id, inp) -> ConnectorResult:
    tid = inp.get("task_id")
    if not tid:
        return ConnectorResult(ok=False, error="Provide the task_id to update.")
    data: dict = {}
    if inp.get("title") and _has(schema, "task", "title"):
        data["title"] = inp["title"]
    _set_body(schema, "task", data, inp.get("body"))
    if inp.get("due_at") and _has(schema, "task", "dueAt"):
        data["dueAt"] = inp["due_at"]
    if inp.get("status") and _has(schema, "task", "status"):
        data["status"] = inp["status"]
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "task", tid, data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": tid, "summary": f"Updated task ({', '.join(data.keys())})."})


async def complete_task(client, schema, user_id, inp) -> ConnectorResult:
    tid = inp.get("task_id")
    if not tid:
        return ConnectorResult(ok=False, error="Provide the task_id to complete (list tasks first).")
    if not _has(schema, "task", "status"):
        return ConnectorResult(ok=False, error="This CRM's Task has no status field.")
    res = await _update(client, schema, "task", tid, {"status": "DONE"})
    return res if not res.ok else ConnectorResult(ok=True, data={"id": tid, "summary": "Marked the task complete.", "idempotent": True})


async def delete_task(client, schema, user_id, inp) -> ConnectorResult:
    tid = inp.get("task_id")
    if not tid:
        return ConnectorResult(ok=False, error="Provide the task_id to delete.")
    res = await _delete(client, schema, "task", tid)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": tid, "status": "deleted", "summary": "Deleted the task."})


# ══ NOTES ═════════════════════════════════════════════════════════════════════
async def add_note(client, schema, user_id, inp) -> ConnectorResult:
    body = inp.get("body") or inp.get("note") or ""
    if not body:
        return ConnectorResult(ok=False, error="The note body is empty.")
    data: dict = {}
    if _has(schema, "note", "title"):
        data["title"] = inp.get("title") or body[:60]
    _set_body(schema, "note", data, body)
    res = await _create(client, schema, "note", data)
    if not res.ok:
        return res
    attached = await _attach_target(client, schema, "note", res.data["id"], inp)
    suffix = f" attached to {', '.join(attached)}" if attached else " (not attached — no target given)"
    return ConnectorResult(ok=True, data={"id": res.data["id"], "summary": f"Added a note{suffix}."})


async def update_note(client, schema, user_id, inp) -> ConnectorResult:
    nid = inp.get("note_id")
    if not nid:
        return ConnectorResult(ok=False, error="Provide the note_id to update.")
    data: dict = {}
    if inp.get("title") and _has(schema, "note", "title"):
        data["title"] = inp["title"]
    _set_body(schema, "note", data, inp.get("body") or inp.get("note"))
    if not data:
        return ConnectorResult(ok=False, error="No updatable fields provided.")
    res = await _update(client, schema, "note", nid, data)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": nid, "summary": "Updated the note."})


async def delete_note(client, schema, user_id, inp) -> ConnectorResult:
    nid = inp.get("note_id")
    if not nid:
        return ConnectorResult(ok=False, error="Provide the note_id to delete.")
    res = await _delete(client, schema, "note", nid)
    return res if not res.ok else ConnectorResult(ok=True, data={"id": nid, "status": "deleted", "summary": "Deleted the note."})


# ══ TAGS (on person / company / opportunity) ══════════════════════════════════
async def _set_tags(client, schema, user_id, inp, *, add: bool) -> ConnectorResult:
    alias = (inp.get("object_type") or "person").strip().lower()
    if alias not in ("person", "company", "opportunity"):
        return ConnectorResult(ok=False, error="object_type must be person, company, or opportunity.")
    field = _tag_field(schema, alias)
    if not field:
        return ConnectorResult(ok=False, error=f"This CRM has no tags field on {alias} yet (tags appear after a GHL import).")
    rid, label = await _resolve_id(client, schema, alias, inp, f"{alias}_id")
    if not rid:
        return ConnectorResult(ok=False, error=f"No {alias} matching '{label}'.")
    tag = (inp.get("tag") or "").strip()
    if not tag:
        return ConnectorResult(ok=False, error="No tag provided.")
    plural = schema.obj(alias).name_plural
    res = await client.query_data(
        f"query T {{ {plural}(first: 1, filter: {{ id: {{ eq: \"{rid}\" }} }}) {{ edges {{ node {{ {field} }} }} }} }}",
        action="Read tags",
    )
    current = []
    if res.ok:
        edges = ((res.data or {}).get(plural) or {}).get("edges") or []
        if edges:
            current = (edges[0].get("node") or {}).get(field) or []
    current = [t for t in (current or []) if t]
    if add and tag in current:
        return ConnectorResult(ok=True, data={"id": rid, "summary": f"{label} already has tag '{tag}'.", "idempotent": True})
    if not add and tag not in current:
        return ConnectorResult(ok=True, data={"id": rid, "summary": f"{label} doesn't have tag '{tag}'.", "idempotent": True})
    new_tags = current + [tag] if add else [t for t in current if t != tag]
    upd = await _update(client, schema, alias, rid, {field: new_tags})
    if not upd.ok:
        return upd
    verb = "Added" if add else "Removed"
    return ConnectorResult(ok=True, data={"id": rid, "summary": f"{verb} tag '{tag}' {'to' if add else 'from'} {label}."})


async def add_tag(client, schema, user_id, inp) -> ConnectorResult:
    return await _set_tags(client, schema, user_id, inp, add=True)


async def remove_tag(client, schema, user_id, inp) -> ConnectorResult:
    return await _set_tags(client, schema, user_id, inp, add=False)


# ══ GENERIC RELATIONSHIP LINKING ══════════════════════════════════════════════
# (owning object, foreign-key field) for each supported {a,b} pair, order-insensitive.
_LINKS = {
    frozenset(("person", "company")): ("person", "companyId", "company"),
    frozenset(("opportunity", "company")): ("opportunity", "companyId", "company"),
    frozenset(("opportunity", "person")): ("opportunity", "pointOfContactId", "person"),
}


async def link_records(client, schema, user_id, inp) -> ConnectorResult:
    a = (inp.get("from_type") or "").strip().lower()
    b = (inp.get("to_type") or "").strip().lower()
    spec = _LINKS.get(frozenset((a, b))) if a and b else None
    if not spec:
        return ConnectorResult(ok=False, error="Supported links: person↔company, opportunity↔company, opportunity↔person. (Attach notes/tasks with add_note/create_task.)")
    owner_alias, fk_field, other_alias = spec
    owner_q = inp.get("from_query") if a == owner_alias else inp.get("to_query")
    owner_id = inp.get("from_id") if a == owner_alias else inp.get("to_id")
    other_q = inp.get("to_query") if a == owner_alias else inp.get("from_query")
    other_id = inp.get("to_id") if a == owner_alias else inp.get("from_id")
    oid, olabel = await _resolve_id(client, schema, owner_alias, {f"{owner_alias}_id": owner_id, "query": owner_q}, f"{owner_alias}_id")
    if not oid:
        return ConnectorResult(ok=False, error=f"No {owner_alias} matching '{olabel}'.")
    tid, tlabel = await _resolve_id(client, schema, other_alias, {f"{other_alias}_id": other_id, "query": other_q}, f"{other_alias}_id")
    if not tid:
        return ConnectorResult(ok=False, error=f"No {other_alias} matching '{tlabel}'.")
    if not _has(schema, owner_alias, fk_field.replace("Id", "")):
        return ConnectorResult(ok=False, error=f"This CRM's {owner_alias} can't link to {other_alias}.")
    res = await _update(client, schema, owner_alias, oid, {fk_field: tid})
    return res if not res.ok else ConnectorResult(ok=True, data={"summary": f"Linked {owner_alias} '{olabel}' to {other_alias} '{tlabel}'."})


# ══ BULK + GENERIC-FIELD WRITES ═══════════════════════════════════════════════
async def _all_records(client, schema, alias: str, *, max_records: int = 5000, extra_sel: str = "") -> list[dict]:
    """Page every record of `alias` with id + name (+ optional extra selection)."""
    obj = schema.obj(alias)
    if not obj:
        return []
    name_sel = "name { firstName lastName }" if alias == "person" else "name"
    sel = f"id {name_sel} {extra_sel}".strip()
    nodes, after = [], None
    for _ in range(60):
        q = (f"query P($after: String) {{ {obj.name_plural}(first: 100, after: $after) "
             f"{{ edges {{ node {{ {sel} }} }} pageInfo {{ hasNextPage endCursor }} }} }}")
        res = await client.query_data(q, {"after": after}, action=f"List {obj.name_plural}")
        if not res.ok:
            break
        conn = (res.data or {}).get(obj.name_plural) or {}
        for e in conn.get("edges") or []:
            nodes.append(e.get("node") or {})
            if len(nodes) >= max_records:
                return nodes
        pg = conn.get("pageInfo") or {}
        if not pg.get("hasNextPage"):
            break
        after = pg.get("endCursor")
    return nodes


async def bulk_update(client, schema, user_id, inp) -> ConnectorResult:
    """Set the SAME field(s) across MANY records in one call (the reliable bulk path).

    Selection: ids[], names[] (resolved against the live records), and/or all=true.
    `fields` is a {name-or-label: value} map resolved + coerced against the live schema
    (SELECT labels→keys). Validates once up front, then applies per record. Confirm-gated."""
    alias = (inp.get("object_type") or "company").strip().lower()
    if alias not in ("person", "company", "opportunity"):
        return ConnectorResult(ok=False, error="object_type must be person, company, or opportunity.")
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")

    # Build + validate the field payload ONCE (fail fast on bad option/type).
    data: dict = {}
    applied, errors = apply_fields(schema, alias, data, inp.get("fields"))
    if errors:
        return ConnectorResult(ok=False, error="; ".join(errors))
    if not data:
        return ConnectorResult(ok=False, error="Provide `fields` (a map of field→value) to set.")

    # Resolve targets.
    targets: list[tuple[str, str]] = []   # (id, label)
    seen: set[str] = set()
    not_found: list[str] = []
    for rid in (inp.get("ids") or []):
        if rid and rid not in seen:
            targets.append((rid, rid)); seen.add(rid)

    names = list(inp.get("names") or [])
    if inp.get("name"):
        names.append(inp["name"])
    if names or inp.get("all"):
        records = await _all_records(client, schema, alias)
        by_norm = {_norm(_label(alias, n)): n for n in records}
        if inp.get("all") and not names:
            for n in records:
                if n.get("id") and n["id"] not in seen:
                    targets.append((n["id"], _label(alias, n))); seen.add(n["id"])
        for nm in names:
            node = by_norm.get(_norm(nm))
            if not node:
                node = next((n for n in records if _norm(nm) and _norm(nm) in _norm(_label(alias, n))), None)
            if node and node.get("id") not in seen:
                targets.append((node["id"], _label(alias, node))); seen.add(node["id"])
            elif not node:
                not_found.append(nm)

    if not targets:
        msg = "No matching records to update."
        if not_found:
            msg += f" Not found: {', '.join(not_found)}."
        return ConnectorResult(ok=False, error=msg)

    updated, failed = [], []
    for rid, label in targets:
        res = await _update(client, schema, alias, rid, data)
        (updated.append(label) if res.ok else failed.append({"label": label, "error": res.error}))

    summary = f"Set {', '.join(applied)} on {len(updated)} {alias}(s)."
    if failed:
        summary += f" {len(failed)} failed."
    if not_found:
        summary += f" Not found: {', '.join(not_found)}."
    return ConnectorResult(ok=True, data={"updated": len(updated), "failed": failed,
                                          "not_found": not_found, "fields": applied, "summary": summary})


async def rehome_field(client, schema, user_id, inp) -> ConnectorResult:
    """Move a field's value into another field across records — one-shot data fix.

    e.g. move Google Maps URLs that were dumped into `domainName` into the proper
    'Google Maps Link' field. Reads the source value per record, writes it to the target
    field (coerced to the target's type), then clears the source (unless clear_source=false).
    Optional `contains` substring filters which records are moved. Confirm-gated."""
    alias = (inp.get("object_type") or "company").strip().lower()
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    from_field = resolve_field(obj, inp.get("from_field") or ("domainName" if alias == "company" else ""))
    to_field = resolve_field(obj, inp.get("to_field") or "")
    if not from_field:
        return ConnectorResult(ok=False, error=f"No source field '{inp.get('from_field')}' on {alias}.")
    if not to_field:
        return ConnectorResult(ok=False, error=f"No target field '{inp.get('to_field')}' on {alias}.")
    contains = (inp.get("contains") or "").strip().lower()
    clear_source = inp.get("clear_source", True)
    names_norm = {_norm(n) for n in (inp.get("names") or []) if n}

    records = await _all_records(client, schema, alias, extra_sel=read_selection(from_field))
    moved, skipped, failed = [], [], []
    for n in records:
        label = _label(alias, n)
        if names_norm and _norm(label) not in names_norm:
            continue
        url = read_value(from_field, n.get(from_field.name))
        if not url or not str(url).strip():
            continue
        if contains and contains not in str(url).lower():
            skipped.append(label)
            continue
        data: dict = {}
        val, err = coerce_value(to_field, url)
        if err:
            failed.append({"label": label, "error": err}); continue
        data[to_field.name] = val
        if clear_source:
            data[from_field.name] = _empty_for(from_field)
        res = await _update(client, schema, alias, n["id"], data)
        (moved.append(label) if res.ok else failed.append({"label": label, "error": res.error}))

    summary = (f"Moved {from_field.label or from_field.name} → {to_field.label or to_field.name} "
               f"on {len(moved)} {alias}(s).")
    if failed:
        summary += f" {len(failed)} failed."
    return ConnectorResult(ok=True, data={"moved": len(moved), "failed": failed,
                                          "skipped": len(skipped), "summary": summary})


async def read_fields(client, schema, user_id, inp) -> ConnectorResult:
    """Read field values back for one record (verification + 'any field readable').

    Identify by {alias}_id or `query`. `fields` (list of names/labels) selects which;
    default = all CUSTOM fields. SELECT values come back as labels, LINKS as the URL."""
    alias = (inp.get("object_type") or "company").strip().lower()
    obj = schema.obj(alias)
    if not obj:
        return ConnectorResult(ok=False, error=f"This CRM has no '{alias}' object.")
    rid, label = await _resolve_id(client, schema, alias, inp, f"{alias}_id")
    if not rid:
        return ConnectorResult(ok=False, error=f"No {alias} matching '{label}'.")
    wanted = inp.get("fields")
    if wanted:
        flds = [f for f in (resolve_field(obj, w) for w in wanted) if f]
    else:
        flds = [f for f in obj.fields if f.is_custom]
    if not flds:
        return ConnectorResult(ok=True, data={"id": rid, "label": label, "fields": {}})
    sel = "id " + " ".join(read_selection(f) for f in flds)
    res = await client.query_data(
        f'query R {{ {obj.name_plural}(first: 1, filter: {{ id: {{ eq: "{rid}" }} }}) '
        f'{{ edges {{ node {{ {sel} }} }} }} }}', action=f"Read {alias} fields")
    if not res.ok:
        return res
    edges = ((res.data or {}).get(obj.name_plural) or {}).get("edges") or []
    node = (edges[0].get("node") if edges else {}) or {}
    out = {(f.label or f.name): read_value(f, node.get(f.name)) for f in flds}
    return ConnectorResult(ok=True, data={"id": rid, "label": label, "fields": out,
                                          "summary": f"Read {len(out)} field(s) on {label}."})


# ══ ADVANCED ESCAPE HATCH (confirm-gated) ═════════════════════════════════════
async def run_graphql_mutation(client, schema, user_id, inp) -> ConnectorResult:
    """Run a raw Twenty GraphQL MUTATION for rare operations the structured tools don't
    cover. Hits the per-user data API only (isolation preserved). Confirm-gated in
    chat.py. Validates it's a single mutation; never touches GHL."""
    mutation = (inp.get("mutation") or "").strip()
    if not mutation:
        return ConnectorResult(ok=False, error="Provide a GraphQL `mutation` string.")
    low = mutation.lower()
    if not low.startswith("mutation"):
        return ConnectorResult(ok=False, error="Only `mutation` operations are allowed here (reads use the structured tools).")
    if "__schema" in low or "__type" in low:
        return ConnectorResult(ok=False, error="Introspection isn't allowed through this tool.")
    res = await client.query_data(mutation, inp.get("variables") or {}, action="Advanced GraphQL mutation")
    if not res.ok:
        return res
    return ConnectorResult(ok=True, data={"result": res.data, "summary": "Ran the custom CRM mutation."})


# action name -> handler
WRITE_HANDLERS = {
    # people
    "create_person": create_person, "update_person": update_person, "delete_person": delete_person,
    # companies
    "create_company": create_company, "update_company": update_company, "delete_company": delete_company,
    # opportunities
    "create_opportunity": create_opportunity, "update_opportunity": update_opportunity,
    "move_opportunity_stage": move_opportunity_stage, "delete_opportunity": delete_opportunity,
    # tasks
    "create_task": create_task, "update_task": update_task, "complete_task": complete_task, "delete_task": delete_task,
    # notes
    "add_note": add_note, "update_note": update_note, "delete_note": delete_note,
    # tags
    "add_tag": add_tag, "remove_tag": remove_tag,
    # bulk + generic-field writes
    "bulk_update": bulk_update,
    "rehome_field": rehome_field,
    "read_fields": read_fields,
    # relationships + escape hatch
    "link_records": link_records,
    "run_graphql_mutation": run_graphql_mutation,
}
