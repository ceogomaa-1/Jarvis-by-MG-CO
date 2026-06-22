"""
Step 6 — twenty__* agent tools: let Jarvis read/operate the owned CRM.

Dispatched specially in tool_executor (connector_type == "twenty"), built from env
(not a per-user connector). Read-only over the imported data:

  twenty__list_people
  twenty__search_people
  twenty__list_opportunities                (optionally filtered to a stage)
  twenty__count_opportunities_in_stage
  twenty__person_notes_tasks

Filtering is done client-side after paging, to avoid Twenty's version-sensitive
GraphQL filter DSL — correctness over cleverness for Phase 1.
"""
from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import writes
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import TwentySchema, introspect

_MAX_PAGES = 25
_PAGE = 100


async def _page(client: TwentyClient, plural: str, node_fields: str, *, max_records: int) -> list[dict]:
    nodes: list[dict] = []
    after = None
    for _ in range(_MAX_PAGES):
        query = f"""
        query Page($after: String) {{
          {plural}(first: {_PAGE}, after: $after) {{
            edges {{ node {{ {node_fields} }} }}
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
        """
        res = await client.query_data(query, {"after": after}, action=f"List {plural}")
        if not res.ok:
            break
        conn = (res.data or {}).get(plural) or {}
        for edge in conn.get("edges") or []:
            nodes.append(edge.get("node") or {})
            if len(nodes) >= max_records:
                return nodes
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    return nodes


def _full_name(node: dict) -> str:
    n = node.get("name") or {}
    if isinstance(n, dict):
        return f"{n.get('firstName', '')} {n.get('lastName', '')}".strip()
    return str(n or "")


def _primary_email(node: dict) -> str:
    e = node.get("emails") or {}
    return e.get("primaryEmail", "") if isinstance(e, dict) else ""


def _stage_field_names(targets: dict[str, list[tuple[str, str]]]) -> list[str]:
    names = {fn for pairs in targets.values() for fn, _ in pairs}
    return sorted(names)


async def execute_twenty_tool(action_name: str, inp: dict, user_id: str) -> ConnectorResult:
    # Resolve THIS user's workspace (Phase 2) — their own tenant key, or the shared
    # instance as fallback. The per-user key is the data-isolation boundary: it can
    # only ever read/write its own workspace's records.
    client = await TwentyClient.for_user(user_id)
    if not client:
        return ConnectorResult(ok=False, error="Jarvis CRM is not configured for this account.")

    schema_res = await introspect(client)
    schema: TwentySchema = schema_res.data
    if not schema or not schema.obj("person"):
        return ConnectorResult(ok=False, error=f"Could not read Twenty schema: {schema_res.error}")

    people_plural = schema.obj("person").name_plural
    opp_obj = schema.obj("opportunity")
    opp_plural = opp_obj.name_plural if opp_obj else "opportunities"

    # ── WRITE actions (Phase 3) — scoped to this user's workspace via for_user above.
    # Destructive ones (delete_*) are gated by chat.py WRITE_ACTIONS before reaching here.
    write_handler = writes.WRITE_HANDLERS.get(action_name)
    if write_handler:
        return await write_handler(client, schema, user_id, inp)

    if action_name in ("list_people", "search_people"):
        limit = int(inp.get("limit", 25))
        people = await _page(client, people_plural, "id name { firstName lastName } emails { primaryEmail }", max_records=500 if action_name == "search_people" else limit)
        rows = [{"id": p.get("id"), "name": _full_name(p), "email": _primary_email(p)} for p in people]
        if action_name == "search_people":
            q = (inp.get("query") or "").strip().lower()
            rows = [r for r in rows if q in r["name"].lower() or q in r["email"].lower()][:limit]
        return ConnectorResult(ok=True, data={"count": len(rows), "people": rows})

    if action_name in ("list_companies", "search_companies"):
        co_obj = schema.obj("company")
        if not co_obj:
            return ConnectorResult(ok=False, error="This CRM has no Company object.")
        limit = int(inp.get("limit", 25))
        cos = await _page(client, co_obj.name_plural, "id name", max_records=500 if action_name == "search_companies" else limit)
        rows = [{"id": c.get("id"), "name": c.get("name")} for c in cos]
        if action_name == "search_companies":
            q = (inp.get("query") or "").strip().lower()
            rows = [r for r in rows if q in (r["name"] or "").lower()][:limit]
        return ConnectorResult(ok=True, data={"count": len(rows), "companies": rows})

    if action_name in ("list_opportunities", "count_opportunities_in_stage"):
        # Stages resolve from the GHL import map AND Twenty's native stage options.
        targets = await writes.stage_label_map(user_id, schema)
        stage_fields = _stage_field_names(targets)
        field_sel = " ".join(stage_fields)
        opps = await _page(client, opp_plural, f"id name {field_sel}".strip(), max_records=2000)

        wanted_label = (inp.get("stage") or "").strip().lower()
        wanted_pairs = targets.get(wanted_label, []) if wanted_label else []

        def _in_stage(node: dict) -> bool:
            if not wanted_pairs:
                return True
            return any(node.get(fn) == val for fn, val in wanted_pairs)

        if wanted_label and not wanted_pairs:
            known = sorted({lbl for lbl in targets})
            return ConnectorResult(ok=False, error=f"No stage matching '{inp.get('stage')}'. Known stages: {', '.join(known) or 'none (run the import first)'}.")

        matched = [o for o in opps if _in_stage(o)]
        if action_name == "count_opportunities_in_stage":
            return ConnectorResult(ok=True, data={"stage": inp.get("stage"), "count": len(matched)})
        limit = int(inp.get("limit", 50))
        rows = [{"id": o.get("id"), "name": o.get("name")} for o in matched[:limit]]
        return ConnectorResult(ok=True, data={"count": len(matched), "opportunities": rows})

    if action_name == "person_notes_tasks":
        q = (inp.get("query") or "").strip().lower()
        people = await _page(client, people_plural, "id name { firstName lastName } emails { primaryEmail }", max_records=500)
        match = next((p for p in people if q in _full_name(p).lower() or q in _primary_email(p).lower()), None)
        if not match:
            return ConnectorResult(ok=False, error=f"No person matching '{inp.get('query')}' in the owned CRM.")
        person_id = match.get("id")
        notes = await _read_targets(client, "noteTargets", "note", person_id)
        tasks = await _read_targets(client, "taskTargets", "task", person_id)
        return ConnectorResult(ok=True, data={
            "person": {"id": person_id, "name": _full_name(match), "email": _primary_email(match)},
            "notes": notes, "tasks": tasks,
        })

    return ConnectorResult(ok=False, error=f"Unknown Twenty action: {action_name}")


async def _read_targets(client: TwentyClient, target_plural: str, child: str, person_id: str) -> list[dict]:
    """Best-effort read of a person's notes/tasks via the target join object.

    Twenty's join filter field is `targetPersonId` (not `personId`), and the body lives
    in `bodyV2` (RICH_TEXT) on current Twenty — fall back to legacy `body` if needed."""
    for body_sel, getter in (("bodyV2 { markdown }", lambda n: (n.get("bodyV2") or {}).get("markdown")),
                             ("body", lambda n: n.get("body"))):
        query = f"""
        query Targets {{
          {target_plural}(first: 100, filter: {{ targetPersonId: {{ eq: "{person_id}" }} }}) {{
            edges {{ node {{ {child} {{ id title {body_sel} }} }} }}
          }}
        }}
        """
        res = await client.query_data(query, action=f"Read {target_plural}")
        if not res.ok:
            continue
        out = []
        for edge in ((res.data or {}).get(target_plural) or {}).get("edges") or []:
            node = (edge.get("node") or {}).get(child) or {}
            if node:
                out.append({"title": node.get("title"), "body": getter(node)})
        return out
    return []
