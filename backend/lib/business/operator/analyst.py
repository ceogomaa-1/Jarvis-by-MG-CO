"""
Operator Cycle 0 — ANALYST (Batch 71: Co-Founder Mode).

The co-founder's walk through the business before proposing anything.
Deterministic and LLM-free: pulls REAL state from every wired system in
parallel — CRM pipeline, scored leads, inbox, calendar, revenue, social
queue — plus the owner's past approve/decline decisions so the strategist
learns what this owner actually ships.

Every source is fail-soft: a missing connector or a flaky API becomes a
"not connected / unavailable" line in the digest, never an exception that
kills the run.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_SOURCE_TIMEOUT = 25.0  # per-source hard cap so one slow API can't stall the scan


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


async def _with_timeout(coro, source: str):
    try:
        return await asyncio.wait_for(coro, timeout=_SOURCE_TIMEOUT)
    except asyncio.TimeoutError:
        return {"ok": False, "note": f"{source} scan timed out"}
    except Exception as e:
        return {"ok": False, "note": f"{source} scan error: {str(e)[:120]}"}


# ─────────────────────────────────────────────────────────────────────
# Individual scanners — each returns {"ok": bool, ...facts} and never raises
# ─────────────────────────────────────────────────────────────────────

async def _scan_crm(user_id: str) -> dict:
    """Rue CRM (Twenty): pipeline totals, stage distribution, stale deals."""
    from backend.lib.business.twenty.tools import execute_twenty_tool

    opps_res = await execute_twenty_tool("list_opportunities", {"limit": 60}, user_id)
    if not opps_res.ok:
        return {"ok": False, "note": opps_res.error or "CRM not configured"}

    data = opps_res.data or {}
    opps = data.get("opportunities") or data.get("records") or data.get("items") or []
    if isinstance(opps, dict):
        opps = list(opps.values())

    by_stage: dict[str, int] = {}
    total_value = 0.0
    stale = []
    now = datetime.now(timezone.utc)
    for o in opps:
        if not isinstance(o, dict):
            continue
        stage = str(o.get("stage") or o.get("Stage") or "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        amt = o.get("amount")
        if isinstance(amt, dict):
            amt = amt.get("amountMicros")
            if amt:
                try:
                    total_value += float(amt) / 1_000_000
                except (TypeError, ValueError):
                    pass
        elif isinstance(amt, (int, float)):
            total_value += float(amt)
        updated = o.get("updatedAt") or o.get("updated_at") or ""
        try:
            upd_dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            if (now - upd_dt).days >= 14:
                stale.append(o.get("name") or "unnamed deal")
        except (TypeError, ValueError):
            pass

    companies_res = await execute_twenty_tool("list_companies", {"limit": 1}, user_id)
    companies_note = ""
    if companies_res.ok:
        cdata = companies_res.data or {}
        total_companies = cdata.get("total") or cdata.get("count")
        if total_companies:
            companies_note = f"{total_companies} companies tracked."

    return {
        "ok": True,
        "open_opportunities": len(opps),
        "pipeline_by_stage": by_stage,
        "pipeline_value_usd": round(total_value, 2),
        "stale_deals_14d": stale[:8],
        "stale_count": len(stale),
        "companies_note": companies_note,
    }


async def _scan_leads(user_id: str) -> dict:
    """mgcoleads: scored A/B/C leads sitting un-actioned."""
    from backend.lib.business.leads.tools import execute_leads_tool

    res = await execute_leads_tool("list_leads", {"limit": 100}, user_id)
    if not res.ok:
        return {"ok": False, "note": res.error or "Leads engine not enabled"}

    data = res.data or {}
    leads = data.get("leads") or data.get("items") or []
    grades: dict[str, int] = {}
    hot = []
    for l in leads:
        if not isinstance(l, dict):
            continue
        g = str(l.get("grade") or l.get("score_grade") or "?").upper()
        grades[g] = grades.get(g, 0) + 1
        if g == "A" and len(hot) < 6:
            hot.append(l.get("name") or l.get("business_name") or "unnamed")
    return {"ok": True, "total_scored": len(leads), "by_grade": grades, "top_a_leads": hot}


async def _scan_google(user_id: str) -> dict:
    """Gmail + Calendar: unread that needs answers, and the next 7 days."""
    from backend.lib.business.connectors.registry import get_connector_for_user

    connector = await get_connector_for_user(user_id, "google")
    if not connector:
        return {"ok": False, "note": "Google not connected"}

    out: dict = {"ok": True}
    try:
        emails = await connector.list_emails(max_results=15, query="is:unread")
        if emails.ok:
            msgs = (emails.data or {}).get("messages") or (emails.data or {}).get("emails") or []
            out["unread_count"] = len(msgs)
            out["unread_subjects"] = [
                (m.get("subject") or "(no subject)")[:80] for m in msgs[:6] if isinstance(m, dict)
            ]
    except Exception as e:
        out["email_note"] = f"inbox scan failed: {str(e)[:80]}"

    try:
        events = await connector.list_calendar_events(max_results=15)
        if events.ok:
            evs = (events.data or {}).get("events") or []
            out["upcoming_events"] = len(evs)
            out["next_events"] = [
                f"{e.get('summary','(untitled)')} @ {e.get('start','')}"[:90]
                for e in evs[:5] if isinstance(e, dict)
            ]
    except Exception as e:
        out["calendar_note"] = f"calendar scan failed: {str(e)[:80]}"
    return out


async def _scan_stripe(user_id: str) -> dict:
    from backend.lib.business.connectors.registry import get_connector_for_user

    connector = await get_connector_for_user(user_id, "stripe")
    if not connector:
        return {"ok": False, "note": "Stripe not connected"}
    res = await connector.revenue_summary_last_30_days()
    if not res.ok:
        return {"ok": False, "note": res.error or "Stripe summary failed"}
    return {"ok": True, **(res.data or {})}


async def _scan_buffer(user_id: str) -> dict:
    """Social queue: is anything scheduled, or has posting gone dark?"""
    from backend.lib.business.connectors.registry import get_connector_for_user

    connector = await get_connector_for_user(user_id, "buffer")
    if not connector:
        return {"ok": False, "note": "Buffer not connected"}
    try:
        res = await connector.get_scheduled_posts(channel_ids=None, limit=20, organization_id=None)
    except TypeError:
        res = await connector.get_scheduled_posts(limit=20)
    if not res.ok:
        return {"ok": False, "note": res.error or "Buffer scan failed"}
    posts = (res.data or {}).get("posts") or (res.data or {}).get("updates") or []
    return {"ok": True, "scheduled_posts": len(posts)}


async def _scan_qna(user_id: str) -> dict:
    """The detective's case file: answered facts + questions still open."""
    from backend.lib.business.cofounder_questions import answers_digest, list_questions

    answered = await answers_digest(user_id, limit=8)
    open_rows = await list_questions(user_id, status="open", limit=10)
    return {
        "ok": True,
        "answers": answered,
        "open_questions": [r.get("question", "") for r in open_rows],
    }


async def _scan_decision_history(user_id: str) -> dict:
    """What did the owner approve, decline, and why — the learning signal."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"ok": False, "note": "no supabase"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_read_headers(),
                params={
                    "select": "title,action_type,status,decline_reason,created_at",
                    "user_id": f"eq.{user_id}",
                    "status": "in.(shipped,executed,discarded,execution_failed)",
                    "order": "created_at.desc",
                    "limit": "25",
                },
                timeout=10.0,
            )
        if resp.status_code != 200:
            # decline_reason column may not exist pre-migration — retry without it
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                    headers=_read_headers(),
                    params={
                        "select": "title,action_type,status,created_at",
                        "user_id": f"eq.{user_id}",
                        "status": "in.(shipped,discarded)",
                        "order": "created_at.desc",
                        "limit": "25",
                    },
                    timeout=10.0,
                )
        if resp.status_code != 200:
            return {"ok": False, "note": f"history fetch {resp.status_code}"}
        rows = resp.json()
        approved = [r["title"] for r in rows if r.get("status") in ("shipped", "executed")][:8]
        declined = [
            f"{r['title']}" + (f" (reason: {r['decline_reason']})" if r.get("decline_reason") else "")
            for r in rows if r.get("status") == "discarded"
        ][:8]
        return {"ok": True, "approved": approved, "declined": declined, "total": len(rows)}
    except Exception as e:
        return {"ok": False, "note": f"history error: {str(e)[:100]}"}


# ─────────────────────────────────────────────────────────────────────
# Digest builder
# ─────────────────────────────────────────────────────────────────────

def _fmt_section(title: str, body: str) -> str:
    return f"### {title}\n{body.strip()}\n"


def build_digest(snapshot: dict) -> str:
    """Human/LLM-readable digest of the scan — what the strategist reads."""
    s = snapshot.get("sections", {})
    parts: list[str] = []

    crm = s.get("crm", {})
    if crm.get("ok"):
        stages = ", ".join(f"{k}: {v}" for k, v in (crm.get("pipeline_by_stage") or {}).items()) or "none"
        body = (
            f"{crm.get('open_opportunities', 0)} open opportunities "
            f"(~${crm.get('pipeline_value_usd', 0):,.0f} total). Stages — {stages}. "
            f"{crm.get('stale_count', 0)} deals untouched 14+ days"
        )
        if crm.get("stale_deals_14d"):
            body += ": " + ", ".join(crm["stale_deals_14d"])
        body += ". " + (crm.get("companies_note") or "")
        parts.append(_fmt_section("CRM PIPELINE (live)", body))
    else:
        parts.append(_fmt_section("CRM PIPELINE", f"Unavailable — {crm.get('note','not scanned')}"))

    leads = s.get("leads", {})
    if leads.get("ok"):
        grades = ", ".join(f"{k}: {v}" for k, v in (leads.get("by_grade") or {}).items()) or "none scored"
        body = f"{leads.get('total_scored', 0)} scored leads ({grades})."
        if leads.get("top_a_leads"):
            body += " Hot A-grade waiting: " + ", ".join(leads["top_a_leads"]) + "."
        parts.append(_fmt_section("LEAD ENGINE (live)", body))
    else:
        parts.append(_fmt_section("LEAD ENGINE", f"Unavailable — {leads.get('note','not scanned')}"))

    g = s.get("google", {})
    if g.get("ok"):
        body = f"{g.get('unread_count', 0)} unread emails."
        if g.get("unread_subjects"):
            body += " Recent: " + "; ".join(g["unread_subjects"]) + "."
        body += f" {g.get('upcoming_events', 0)} calendar events coming up."
        if g.get("next_events"):
            body += " Next: " + "; ".join(g["next_events"]) + "."
        parts.append(_fmt_section("INBOX + CALENDAR (live)", body))
    else:
        parts.append(_fmt_section("INBOX + CALENDAR", f"Unavailable — {g.get('note','not scanned')}"))

    stripe = s.get("stripe", {})
    if stripe.get("ok"):
        parts.append(_fmt_section(
            "REVENUE (Stripe, last 30d)",
            json.dumps({k: v for k, v in stripe.items() if k != "ok"})[:400],
        ))
    else:
        parts.append(_fmt_section("REVENUE", f"Unavailable — {stripe.get('note','not scanned')}"))

    buf = s.get("buffer", {})
    if buf.get("ok"):
        n = buf.get("scheduled_posts", 0)
        note = "content queue is EMPTY — the brand has gone dark" if n == 0 else f"{n} posts scheduled"
        parts.append(_fmt_section("SOCIAL QUEUE (live)", note + "."))
    else:
        parts.append(_fmt_section("SOCIAL QUEUE", f"Unavailable — {buf.get('note','not scanned')}"))

    hist = s.get("decisions", {})
    if hist.get("ok") and hist.get("total"):
        body = ""
        if hist.get("approved"):
            body += "Owner APPROVED before: " + "; ".join(hist["approved"]) + ". "
        if hist.get("declined"):
            body += "Owner DECLINED before: " + "; ".join(hist["declined"]) + "."
        parts.append(_fmt_section("OWNER DECISION HISTORY (learn from this)", body or "No decisions yet."))

    qna = s.get("qna", {})
    if qna.get("ok"):
        if qna.get("answers"):
            parts.append(_fmt_section(
                "OWNER ANSWERS ON RECORD (facts you asked for — use them, never re-ask)",
                qna["answers"],
            ))
        if qna.get("open_questions"):
            parts.append(_fmt_section(
                "QUESTIONS ALREADY ASKED, STILL UNANSWERED (do NOT re-ask these)",
                "\n".join(f"- {q}" for q in qna["open_questions"]),
            ))

    return "\n".join(parts).strip()


async def run_analyst(user_id: str) -> dict:
    """Run the full parallel scan. Returns {sections, digest, scanned_at, sources_ok}."""
    crm, leads, google, stripe, buffer_s, decisions, qna = await asyncio.gather(
        _with_timeout(_scan_crm(user_id), "CRM"),
        _with_timeout(_scan_leads(user_id), "leads"),
        _with_timeout(_scan_google(user_id), "Google"),
        _with_timeout(_scan_stripe(user_id), "Stripe"),
        _with_timeout(_scan_buffer(user_id), "Buffer"),
        _with_timeout(_scan_decision_history(user_id), "history"),
        _with_timeout(_scan_qna(user_id), "Q&A"),
    )
    sections = {
        "crm": crm, "leads": leads, "google": google,
        "stripe": stripe, "buffer": buffer_s, "decisions": decisions,
        "qna": qna,
    }
    snapshot = {
        "sections": sections,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "sources_ok": [k for k, v in sections.items() if v.get("ok")],
    }
    snapshot["digest"] = build_digest(snapshot)
    return snapshot
