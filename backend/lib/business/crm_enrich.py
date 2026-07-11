"""
Background bulk-enrichment of Rue CRM (Twenty) companies.

THE PROBLEM
  "Get phone numbers for all 42 companies in my CRM" is a per-record bulk op: one Maps
  lookup + one CRM write PER company. Run inside a chat turn it blows past the tool-round
  budget AND the 120s Render request window, and dies with "I hit a processing limit…".

THE FIX
  chat.py detects the bulk-enrichment intent (detect_bulk_enrichment), answers immediately
  ("On it — enriching 42 companies…") and hands the work to run_enrichment() as a DETACHED
  asyncio task. That task:
    1. pulls the target companies (those missing the requested field) from the CRM,
    2. looks each up via the Maps provider — batched with bounded concurrency and a hard
       per-job lookup ceiling (cost guard),
    3. writes each result straight back into the CRM as it's found (guarded write path),
    4. drops a summary back into the conversation when done.
  It runs OUTSIDE the HTTP request, so the Render request can't time out mid-run.

Only phone / website / address are enrichable here — those are what the Maps provider
returns (Google Places has no email; an email-only ask falls through to the chat model,
which explains the limitation honestly).
"""
import asyncio
import os
import re

import httpx

from backend.lib.business.leads import config as leads_config
from backend.lib.business.leads.providers import ProviderError, get_provider
from backend.lib.business.twenty import writes
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import introspect
from backend.lib.business.twenty.tools import execute_twenty_tool

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Cost / rate guards for the detached job.
_CONCURRENCY = 5          # parallel Maps lookups (provider is per-call; be gentle)
_MAX_COMPANIES = 250      # hard ceiling on companies touched in one job (cost guard)
_PAGE = 100
_MAX_PAGES = 30

# Fields this job can enrich, mapped to the normalized key the Maps provider returns.
_PROVIDER_KEY = {"phone": "phone", "website": "website", "address": "address"}

# Candidate company field names/labels to resolve each enrichable field against the live
# schema (resolve_field is case/label tolerant, so these are just hints).
_FIELD_CANDIDATES = {
    "phone": ("phone", "phones", "phoneNumber", "telephone", "mobile", "cell"),
    "website": ("website", "domainName", "domain", "url", "site", "web"),
    "address": ("address", "addressText", "location", "street"),
}

# A field on Company that gives geographic context for a better Maps query (best effort).
_CONTEXT_ADDRESS_CANDIDATES = ("address", "addressText", "location", "city", "billingAddress")


# ── intent detection ──────────────────────────────────────────────────────────
_VERB = re.compile(
    r"\b(get|find|fill|enrich|look\s*up|lookup|fetch|populate|add|update|complete|"
    r"grab|pull|scrape|collect|gather)\b"
)
_SCOPE_ALL = re.compile(r"\b(all|every|each|bulk|the whole|entire)\b")
_COMPANY = re.compile(r"\bcompan(?:y|ies)\b|\bcrm\b|\baccounts?\b|\bbusinesses\b|\bleads?\b")
_FIELD_PATTERNS = {
    "phone": re.compile(r"\bphone(?:\s*numbers?)?\b|\bnumbers?\b|\btelephone\b|\bcontact numbers?\b"),
    "email": re.compile(r"\bemails?\b|\be-?mails?\b"),
    "website": re.compile(r"\bwebsites?\b|\burls?\b|\bweb\s*sites?\b"),
    "address": re.compile(r"\baddress(?:es)?\b|\blocations?\b"),
}
_COUNT = re.compile(r"\b(\d{1,4})\b")


def _extract_count(text: str) -> int | None:
    best = None
    for m in _COUNT.finditer(text):
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        if best is None or n > best:
            best = n
    return best


def detect_bulk_enrichment(message: str) -> dict | None:
    """Return {"fields": [...], "limit": int|None} for a bulk CRM-enrichment ask, else None.

    Deliberately strict to avoid hijacking normal chat: needs an enrichment VERB, a
    contact FIELD (phone/email/website/address), a COMPANY/CRM noun, AND either a bulk
    scope word (all/every/each) or an explicit count > 8.
    """
    text = (message or "").lower()
    if not text or not _COMPANY.search(text) or not _VERB.search(text):
        return None
    fields = [f for f, pat in _FIELD_PATTERNS.items() if pat.search(text)]
    if not fields:
        return None
    n = _extract_count(text)
    bulk = bool(_SCOPE_ALL.search(text)) or bool(n and n > 8)
    if not bulk:
        return None
    return {"fields": fields, "limit": n if (n and n > 8) else None}


# ── schema helpers ────────────────────────────────────────────────────────────
def _resolve_targets(company_obj, fields: list[str]) -> list[dict]:
    """Resolve each requested+supported field to a live Company field.

    Returns [{"requested", "field", "provider_key"}] for fields that (a) the Maps
    provider can supply and (b) actually exist on this CRM's Company object.
    """
    out = []
    for req in fields:
        if req not in _PROVIDER_KEY:
            continue  # e.g. "email" — not available from the Maps provider
        fld = None
        for cand in _FIELD_CANDIDATES.get(req, (req,)):
            fld = writes.resolve_field(company_obj, cand)
            if fld:
                break
        if fld and fld.name not in {"id", "createdAt", "updatedAt", "deletedAt"}:
            out.append({"requested": req, "field": fld, "provider_key": _PROVIDER_KEY[req]})
    return out


async def _page_companies(client: TwentyClient, plural: str, node_fields: str) -> list[dict]:
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
        res = await client.query_data(query, {"after": after}, action="List companies (enrich)")
        if not res.ok:
            break
        conn = (res.data or {}).get(plural) or {}
        for edge in conn.get("edges") or []:
            nodes.append(edge.get("node") or {})
            if len(nodes) >= _MAX_COMPANIES:
                return nodes
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    return nodes


def _city_from_address(addr) -> str:
    if not addr:
        return ""
    if isinstance(addr, dict):
        return addr.get("addressCity") or addr.get("city") or ""
    parts = [p.strip() for p in str(addr).split(",") if p.strip()]
    return parts[1] if len(parts) >= 2 else ""


# ── prepare (runs inside the request — fast: one introspect + one page) ────────
async def prepare(user_id: str, fields: list[str], limit: int | None = None) -> dict:
    """Resolve the work for a bulk-enrichment ask without doing any lookups.

    Returns {"status": ...}:
      "ok"            → has targets; payload + "ack" string included
      "nothing"      → CRM reachable but nothing to enrich; "message" included
      "skip"          → not enrichable here (no Maps key / no CRM / no usable field) →
                         caller should fall through to the chat model
    """
    if not leads_config.leads_enabled():
        return {"status": "skip", "reason": "maps-disabled"}
    if not await TwentyClient.configured_for_user(user_id):
        return {"status": "skip", "reason": "no-crm"}

    client = await TwentyClient.for_user(user_id)
    if not client:
        return {"status": "skip", "reason": "no-crm"}

    schema_res = await introspect(client)
    schema = schema_res.data
    company_obj = schema.obj("company") if schema else None
    if not company_obj:
        return {"status": "skip", "reason": "no-company-object"}

    targets_meta = _resolve_targets(company_obj, fields)
    if not targets_meta:
        return {"status": "skip", "reason": "no-usable-field"}

    # Build the read selection: name + each target field + a best-effort address context.
    selections = ["id", "name"]
    seen = set()
    for tm in targets_meta:
        sel = writes.read_selection(tm["field"])
        if tm["field"].name not in seen:
            selections.append(sel)
            seen.add(tm["field"].name)
    ctx_field = None
    for cand in _CONTEXT_ADDRESS_CANDIDATES:
        f = writes.resolve_field(company_obj, cand)
        if f and f.name not in seen:
            ctx_field = f
            selections.append(writes.read_selection(f))
            seen.add(f.name)
            break

    companies = await _page_companies(client, company_obj.name_plural, " ".join(selections))

    targets: list[dict] = []
    for node in companies:
        missing = []
        for tm in targets_meta:
            val = writes.read_value(tm["field"], node.get(tm["field"].name))
            if not val:
                missing.append(tm["requested"])
        if not missing:
            continue
        city = _city_from_address(node.get(ctx_field.name)) if ctx_field else ""
        targets.append({
            "id": node.get("id"),
            "name": node.get("name") or "",
            "city": city,
            "missing": missing,
        })

    targets = [t for t in targets if t["id"] and t["name"]]
    if limit:
        targets = targets[:limit]
    targets = targets[:_MAX_COMPANIES]

    field_labels = [tm["field"].label or tm["requested"] for tm in targets_meta]
    field_words = ", ".join(dict.fromkeys(fl.lower() for fl in field_labels))

    if not targets:
        return {
            "status": "nothing",
            "message": (
                f"Good news — every company in your CRM already has {field_words} filled in, "
                "so there's nothing to enrich."
            ),
        }

    n = len(targets)
    field_map = [
        {"requested": tm["requested"], "api_name": tm["field"].name, "provider_key": tm["provider_key"]}
        for tm in targets_meta
    ]
    ack = (
        f"On it — enriching {n} compan{'y' if n == 1 else 'ies'} ({field_words}). "
        f"I'll write each one into your CRM live as I find it and report back here when I'm done."
    )
    return {
        "status": "ok",
        "ack": ack,
        "count": n,
        "field_words": field_words,
        "targets": targets,
        "field_map": field_map,
    }


# ── run (detached background task — does the lookups + writes) ─────────────────
async def run_enrichment(user_id: str, conversation_id: str | None, prepared: dict) -> None:
    """Look each target company up via the Maps provider and write the result into the CRM.

    Runs as a detached asyncio task (outside the HTTP request). Bounded concurrency + a hard
    company ceiling keep cost in check. Writes go through the guarded update_company path.
    """
    targets: list[dict] = prepared.get("targets") or []
    field_map: list[dict] = prepared.get("field_map") or []
    field_words: str = prepared.get("field_words", "the requested details")
    total = len(targets)

    provider = get_provider()
    counters = {"updated": 0, "no_match": 0, "failed": 0}

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(t: dict) -> None:
        async with sem:
            query = t["name"] + (f", {t['city']}" if t.get("city") else "")
            try:
                leads, _calls = await provider.search(query, 1)
            except ProviderError as e:
                counters["failed"] += 1
                print(f"CRM_ENRICH: provider error for '{query}': {e}")
                return
            except Exception as e:  # noqa: BLE001 — one bad lookup must not kill the job
                counters["failed"] += 1
                print(f"CRM_ENRICH: lookup error for '{query}': {e}")
                return
            if not leads:
                counters["no_match"] += 1
                return
            hit = leads[0]
            write_fields: dict = {}
            for fm in field_map:
                if fm["requested"] not in t["missing"]:
                    continue
                val = hit.get(fm["provider_key"])
                if val:
                    write_fields[fm["api_name"]] = val
            if not write_fields:
                counters["no_match"] += 1
                return
            try:
                res = await execute_twenty_tool(
                    "update_company", {"company_id": t["id"], "fields": write_fields}, user_id
                )
            except Exception as e:  # noqa: BLE001
                counters["failed"] += 1
                print(f"CRM_ENRICH: write error for '{t['name']}': {e}")
                return
            if res.ok:
                counters["updated"] += 1
            else:
                counters["failed"] += 1
                print(f"CRM_ENRICH: write rejected for '{t['name']}': {res.error}")

    try:
        await asyncio.gather(*(_one(t) for t in targets))
    except Exception as e:  # noqa: BLE001
        print(f"CRM_ENRICH: job crashed: {e}")

    summary = _summary_text(counters, total, field_words)
    print(f"CRM_ENRICH: done — {summary}")
    if conversation_id:
        await _post_summary(conversation_id, summary)


def _summary_text(counters: dict, total: int, field_words: str) -> str:
    updated, no_match, failed = counters["updated"], counters["no_match"], counters["failed"]
    parts = [f"Done — I enriched {updated} of {total} companies with {field_words}."]
    extra = []
    if no_match:
        extra.append(f"{no_match} had no match I could find")
    if failed:
        extra.append(f"{failed} couldn't be updated")
    if extra:
        parts.append("(" + "; ".join(extra) + ".)")
    parts.append("They're in your CRM now — refresh to see them.")
    return " ".join(parts)


async def _post_summary(conversation_id: str, text: str) -> None:
    """Append the job's result to the conversation so it shows up back in chat."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/business_messages",
                headers=headers,
                json={"conversation_id": conversation_id, "role": "assistant", "content": text},
                timeout=10.0,
            )
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_conversations",
                headers=headers,
                params={"id": f"eq.{conversation_id}"},
                json={"updated_at": "now()"},
                timeout=10.0,
            )
    except Exception as e:  # noqa: BLE001
        print(f"CRM_ENRICH: summary post error: {e}")


# ── task tracking — keep detached tasks referenced so they aren't GC'd ─────────
_BG_TASKS: set = set()


def track_task(task: asyncio.Task) -> None:
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
