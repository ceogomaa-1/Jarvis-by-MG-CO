"""
compose_home — the Operator pipeline's final step (Batch 67).

Jarvis Home is a fast READ over a precomputed cache. This module is the writer:
it reads the intelligence the rest of Jarvis already produces (Operator runs,
Morning Queue / pending actions, risk flags, metrics, scored leads, calendar) and
composes a fixed set of living, actionable blocks into business_home_blocks.

NON-NEGOTIABLES honored here:
  • Precompute, don't live-call. This runs in the background (nightly operator step
    or on-demand "refresh my home"); the Home view only reads the rows it writes.
  • Explainable ranking. Each block is scored by urgency × value × risk × recency
    over real signals — no black-box LLM ordering. The breakdown is persisted so the
    order is debuggable.
  • Living + acting. Every block carries a primary_action. Most actions inject a
    precise instruction into the docked chat, which executes through the existing
    confirm-gated tool pipeline — so Jarvis acts from Home, it doesn't hand homework.

Summaries are data-driven/templated (no per-block LLM call); the Daily Briefing
reuses the Packager's already-written morning_message when present. That keeps the
compose step cheap and robust even when the account is out of model credits.
"""
import asyncio
import os
import re
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Scoring weights — urgency and value lead, risk close behind, recency a tie-breaker.
# Kept as a module constant so the breakdown stored on each block is self-documenting.
WEIGHTS = {"urgency": 0.30, "value": 0.30, "risk": 0.25, "recency": 0.15}

# Canonical block order / identity. The default layout (home_layout.py) mirrors these keys.
BLOCK_KEYS = [
    "daily_briefing",
    "highest_value_client",
    "biggest_risk",
    "best_lead",
    "urgent_follow_up",
    "pipeline_status",
    "revenue_metrics",
    "calendar_intelligence",
    "tasks_priorities",
    "ai_recommendations",
]


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers(extra: dict | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def score_block(urgency: float, value: float, risk: float, recency: float) -> tuple[float, dict]:
    """Explainable composite score in [0, 100] plus the breakdown to persist.

    Each sub-score is a 0–100 estimate the block builder supplies from real signals.
    """
    def clamp(x: float) -> float:
        return max(0.0, min(100.0, float(x)))

    u, v, r, rec = clamp(urgency), clamp(value), clamp(risk), clamp(recency)
    total = (
        WEIGHTS["urgency"] * u
        + WEIGHTS["value"] * v
        + WEIGHTS["risk"] * r
        + WEIGHTS["recency"] * rec
    )
    breakdown = {
        "urgency": round(u, 1),
        "value": round(v, 1),
        "risk": round(r, 1),
        "recency": round(rec, 1),
        "weights": WEIGHTS,
    }
    return round(total, 2), breakdown


def _recency_from(ts: str | None) -> float:
    """Map an ISO timestamp to a 0–100 recency score (today=100, decaying ~1wk)."""
    if not ts:
        return 30.0
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        if hours <= 12:
            return 100.0
        if hours <= 24:
            return 85.0
        if hours <= 72:
            return 60.0
        if hours <= 168:
            return 40.0
        return 20.0
    except Exception:
        return 30.0


async def _get(client: httpx.AsyncClient, table: str, params: dict) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_read_headers(),
            params=params,
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"HOME_COMPOSE: read {table} failed: {e}")
    return []


# ── signal fetchers ──────────────────────────────────────────────────────────

async def _fetch_signals(client: httpx.AsyncClient, user_id: str) -> dict:
    """Pull every signal Home composes from, concurrently."""
    uid = f"eq.{user_id}"
    tasks = {
        "user": _get(client, "business_users", {
            "select": "industry,company_name", "user_id": uid, "limit": "1"}),
        "metrics": _get(client, "business_user_metrics", {
            "select": "metrics_text,updated_at,created_at", "user_id": uid, "limit": "1"}),
        "flags": _get(client, "business_proactive_messages", {
            "select": "flag_summary,flag_severity,created_at",
            "user_id": uid, "order": "created_at.desc", "limit": "1"}),
        "run": _get(client, "business_operator_runs", {
            "select": "id,status,packager_output,strategist_output,completed_at,started_at",
            "user_id": uid, "order": "started_at.desc", "limit": "1"}),
        "pending": _get(client, "business_pending_actions", {
            "select": "id,action_type,title,description,internal_or_external,connector_type,priority,status,created_at",
            "user_id": uid, "status": "eq.pending",
            "order": "priority.asc,created_at.desc", "limit": "12"}),
        "leads": _get(client, "mgco_leads", {
            "select": "name,score,tier,phone,website,address,category,pushed,created_at",
            "user_id": uid, "order": "score.desc", "limit": "8"}),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    out: dict = {}
    for key, res in zip(tasks.keys(), results):
        out[key] = res if isinstance(res, list) else []
    return out


async def _fetch_calendar(user_id: str) -> str:
    """Best-effort next-events string. Degrades to '' when calendar isn't connected."""
    try:
        from backend.tools.google_calendar import get_calendar_events
        return await asyncio.wait_for(get_calendar_events(user_id, max_results=4), timeout=12.0)
    except Exception as e:
        print(f"HOME_COMPOSE: calendar fetch skipped: {e}")
        return ""


# ── small helpers ────────────────────────────────────────────────────────────

def chat_action(label: str, prompt: str) -> dict:
    """A primary/secondary action that injects an instruction into the docked chat.

    The docked chat runs the full confirm-gated tool pipeline, so this is how Jarvis
    *acts* from Home while keeping every existing safety/connector path."""
    return {"label": label, "kind": "chat", "prompt": prompt}


def nav_action(label: str, target: str) -> dict:
    """Open another surface (crm | leads | workflow | morning_queue | connections)."""
    return {"label": label, "kind": "navigate", "target": target}


def _pct_change(text: str) -> str | None:
    m = re.search(r"([+\-]?\d{1,3})\s?%", text or "")
    return m.group(0).replace(" ", "") if m else None


def _first_sentence(text: str, limit: int = 220) -> str:
    t = (text or "").strip().replace("\n", " ")
    if not t:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    s = parts[0] if parts else t
    return (s[:limit] + "…") if len(s) > limit else s


# ── block builders ───────────────────────────────────────────────────────────
# Each returns a dict in the canonical block shape (sans user_id/run, added later).

def _b_daily_briefing(sig: dict, business_name: str) -> dict:
    run = (sig.get("run") or [{}])[0]
    pkg = run.get("packager_output") or {}
    morning = (pkg.get("morning_message") or "").strip()
    pending_n = len(sig.get("pending") or [])
    flag = (sig.get("flags") or [{}])[0]
    sev = (flag.get("flag_severity") or "none").lower()

    if morning:
        summary = _first_sentence(morning, 260)
    else:
        bits = []
        if pending_n:
            bits.append(f"{pending_n} action{'s' if pending_n != 1 else ''} queued for your review")
        if sev not in ("none", "", "low"):
            bits.append(f"a {sev} risk flag is open")
        summary = ("Overnight I lined up " + " and ".join(bits) + ".") if bits else \
            "I watched the business overnight. Nothing urgent surfaced — here's where things stand."

    urgency = 70 if pending_n else 45
    risk = {"critical": 95, "high": 80, "medium": 55}.get(sev, 25)
    recency = _recency_from(run.get("completed_at") or run.get("started_at"))
    score, breakdown = score_block(urgency, 55, risk, recency)
    return {
        "block_key": "daily_briefing",
        "title": "Daily Briefing",
        "ai_summary": summary or f"Good morning. Here's {business_name} at a glance.",
        "evidence": [
            {"label": "Actions queued", "value": str(pending_n)},
            {"label": "Risk level", "value": sev.title() if sev != "none" else "Clear"},
        ],
        "primary_action": chat_action("Walk me through today",
            "Give me a tight briefing on my business right now: the single most important thing to do today, why it matters, and what you can take off my plate."),
        "secondary_actions": [nav_action("Open Morning Queue", "morning_queue")],
        "status": "ok",
        "score": score,
        "score_breakdown": breakdown,
    }


def _b_highest_value_client(sig: dict) -> dict:
    # CRM is external (Twenty); derive the "highest value" focus from the strongest
    # available signal: a pushed/Tier-A lead, else an external pending action.
    leads = sig.get("leads") or []
    pushed = [l for l in leads if l.get("pushed")]
    pool = pushed or [l for l in leads if (l.get("tier") or "").upper() == "A"] or leads
    ext_actions = [a for a in (sig.get("pending") or []) if a.get("internal_or_external") == "external"]

    if pool:
        top = pool[0]
        name = top.get("name") or "your top account"
        summary = (f"{name} is your highest-value relationship in play"
                   f"{' — already in your CRM' if top.get('pushed') else ''}. "
                   f"Make today the day you move it forward.")
        evidence = [
            {"label": "Account", "value": name},
            {"label": "Fit score", "value": str(top.get("score", "—"))},
        ]
        if top.get("phone"):
            evidence.append({"label": "Phone", "value": top["phone"]})
        primary = chat_action(f"Call {name}",
            f"Help me reach out to {name} ({top.get('phone') or 'find the best contact'}) right now — "
            f"draft what I should say to move this relationship forward, and place the call or send the message.")
        score, breakdown = score_block(70, 90, 40, _recency_from(top.get("created_at")))
        return {
            "block_key": "highest_value_client", "title": "Highest-Value Client Today",
            "ai_summary": summary, "evidence": evidence,
            "primary_action": primary,
            "secondary_actions": [chat_action("Draft a message", f"Draft a short, warm outreach message to {name}.")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    if ext_actions:
        a = ext_actions[0]
        score, breakdown = score_block(65, 75, 35, _recency_from(a.get("created_at")))
        return {
            "block_key": "highest_value_client", "title": "Highest-Value Client Today",
            "ai_summary": f"Your most valuable open move with a client: {a.get('title', '')}.",
            "evidence": [{"label": "Focus", "value": a.get("title", "")}],
            "primary_action": chat_action("Act on this", f"Help me act on this client move now: {a.get('title','')}. {a.get('description','')}"),
            "secondary_actions": [], "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(25, 60, 20, 30)
    return {
        "block_key": "highest_value_client", "title": "Highest-Value Client Today",
        "ai_summary": "Connect your CRM and I'll surface the one client worth your attention today, every morning.",
        "evidence": [], "primary_action": nav_action("Open CRM", "crm"),
        "secondary_actions": [nav_action("Find leads", "leads")],
        "status": "needs_connection", "score": score, "score_breakdown": breakdown,
    }


def _b_biggest_risk(sig: dict) -> dict:
    flag = (sig.get("flags") or [{}])[0]
    summary_txt = (flag.get("flag_summary") or "").strip()
    sev = (flag.get("flag_severity") or "none").lower()
    if summary_txt and sev not in ("none", ""):
        risk = {"critical": 100, "high": 85, "medium": 60, "low": 35}.get(sev, 40)
        urgency = {"critical": 95, "high": 75, "medium": 50, "low": 30}.get(sev, 30)
        score, breakdown = score_block(urgency, 50, risk, _recency_from(flag.get("created_at")))
        return {
            "block_key": "biggest_risk", "title": "Biggest Risk",
            "ai_summary": _first_sentence(summary_txt, 240),
            "evidence": [{"label": "Severity", "value": sev.title()}],
            "primary_action": chat_action("Help me fix this",
                f"Walk me through addressing this risk and take the first step for me: {summary_txt}"),
            "secondary_actions": [chat_action("Explain the exposure", f"Explain why this is a risk and what happens if I ignore it: {summary_txt}")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(15, 30, 20, 40)
    return {
        "block_key": "biggest_risk", "title": "Biggest Risk",
        "ai_summary": "No open risks right now — I'm watching cash, pipeline, and commitments and will flag anything that turns.",
        "evidence": [{"label": "Status", "value": "Clear"}],
        "primary_action": chat_action("Run a risk check", "Scan my business for the biggest risk right now and tell me what to do about it."),
        "secondary_actions": [], "status": "ok", "score": score, "score_breakdown": breakdown,
    }


def _b_best_lead(sig: dict) -> dict:
    leads = sig.get("leads") or []
    fresh = [l for l in leads if not l.get("pushed")]
    pool = fresh or leads
    if pool:
        top = pool[0]
        name = top.get("name") or "a new prospect"
        tier = (top.get("tier") or "").upper()
        summary = (f"{name} is the strongest lead I found"
                   f"{f' — Tier {tier}' if tier else ''}, score {top.get('score','—')}. "
                   f"{top.get('category','') or ''}".strip())
        evidence = [{"label": "Lead", "value": name}, {"label": "Score", "value": str(top.get("score", "—"))}]
        if top.get("website"):
            evidence.append({"label": "Site", "value": top["website"]})
        value = min(100, 50 + int(top.get("score") or 0) // 2)
        score, breakdown = score_block(55, value, 20, _recency_from(top.get("created_at")))
        return {
            "block_key": "best_lead", "title": "Best Lead Discovered Overnight",
            "ai_summary": summary, "evidence": evidence,
            "primary_action": chat_action(f"Pitch {name}",
                f"Draft a tailored cold outreach to {name} ({top.get('website') or top.get('phone') or ''}) and push them into my CRM."),
            "secondary_actions": [nav_action("See all leads", "leads")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(25, 50, 15, 30)
    return {
        "block_key": "best_lead", "title": "Best Lead Discovered Overnight",
        "ai_summary": "Tell me who you sell to and I'll hunt for scored, ready-to-pitch leads every night.",
        "evidence": [], "primary_action": chat_action("Find me leads", "Find and score new B2B leads for my business that I can pitch today."),
        "secondary_actions": [nav_action("Open Leads", "leads")],
        "status": "needs_connection", "score": score, "score_breakdown": breakdown,
    }


def _b_urgent_follow_up(sig: dict) -> dict:
    pending = sig.get("pending") or []
    fu = [a for a in pending if re.search(r"follow|reply|respond|chase|reconnect|overdue|reach\s*out",
                                          f"{a.get('title','')} {a.get('description','')}", re.I)]
    pick = fu[0] if fu else (pending[0] if pending else None)
    if pick:
        is_cold = "cold" in (pick.get("description", "") or "").lower()
        nudge = " Call, don't email." if is_cold else ""
        score, breakdown = score_block(90, 60, 55, _recency_from(pick.get("created_at")))
        return {
            "block_key": "urgent_follow_up", "title": "Urgent Follow-Up",
            "ai_summary": f"This can't wait: {pick.get('title','')}.{nudge}".strip(),
            "evidence": [{"label": "Follow-up", "value": pick.get("title", "")}],
            "primary_action": chat_action("Send the follow-up",
                f"Help me follow up now: {pick.get('title','')}. {pick.get('description','')}. Draft it and send/schedule it for me."),
            "secondary_actions": [chat_action("Draft only", f"Just draft the follow-up for: {pick.get('title','')}")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(20, 40, 25, 35)
    return {
        "block_key": "urgent_follow_up", "title": "Urgent Follow-Up",
        "ai_summary": "Nobody's waiting on you right now. I'll flag the moment a reply slips past due.",
        "evidence": [{"label": "Status", "value": "All caught up"}],
        "primary_action": chat_action("Check for stragglers", "Scan my CRM and inbox for anyone I owe a reply or follow-up and list them."),
        "secondary_actions": [], "status": "ok", "score": score, "score_breakdown": breakdown,
    }


def _b_pipeline_status(sig: dict) -> dict:
    leads = sig.get("leads") or []
    by_tier: dict[str, int] = {}
    for l in leads:
        t = (l.get("tier") or "?").upper()
        by_tier[t] = by_tier.get(t, 0) + 1
    pushed = sum(1 for l in leads if l.get("pushed"))
    pending_n = len(sig.get("pending") or [])
    if leads:
        tier_txt = ", ".join(f"{n} {t}" for t, n in sorted(by_tier.items()))
        summary = f"{len(leads)} scored leads in play ({tier_txt}); {pushed} already in your CRM."
        evidence = [{"label": "Leads", "value": str(len(leads))}, {"label": "In CRM", "value": str(pushed)}]
        status = "ok"
        primary = nav_action("Open Leads pipeline", "leads")
    else:
        summary = "Your pipeline is quiet. Connect a source and I'll keep this honest every morning."
        evidence = [{"label": "Open actions", "value": str(pending_n)}]
        status = "needs_connection"
        primary = nav_action("Open CRM", "crm")
    score, breakdown = score_block(40, 70, 30, 60)
    return {
        "block_key": "pipeline_status", "title": "Pipeline / CRM Status",
        "ai_summary": summary, "evidence": evidence, "primary_action": primary,
        "secondary_actions": [chat_action("Summarize my pipeline", "Give me a one-paragraph health check of my sales pipeline and the next best move.")],
        "status": status, "score": score, "score_breakdown": breakdown,
    }


def _b_revenue_metrics(sig: dict) -> dict:
    m = (sig.get("metrics") or [{}])[0]
    text = (m.get("metrics_text") or "").strip()
    if text:
        change = _pct_change(text)
        head = _first_sentence(text, 180)
        summary = (f"{change} — " if change else "") + head
        value = 80 if change and change.startswith("+") else 65
        score, breakdown = score_block(45, value, 40 if (change and change.startswith("-")) else 25,
                                       _recency_from(m.get("updated_at") or m.get("created_at")))
        return {
            "block_key": "revenue_metrics", "title": "Revenue & Metrics",
            "ai_summary": summary,
            "evidence": ([{"label": "Change", "value": change}] if change else []) +
                        [{"label": "Snapshot", "value": _first_sentence(text, 90)}],
            "primary_action": chat_action("Investigate",
                "Break down what's actually driving my latest numbers — what changed, why, and what I should do about it."),
            "secondary_actions": [chat_action("Update my metrics", "I want to update my latest business metrics.")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(25, 55, 20, 30)
    return {
        "block_key": "revenue_metrics", "title": "Revenue & Metrics",
        "ai_summary": "Share your numbers once and I'll track the trend, flag swings, and explain what moved.",
        "evidence": [], "primary_action": chat_action("Add my metrics", "Help me set up the key revenue and business metrics you should track for me."),
        "secondary_actions": [], "status": "needs_connection", "score": score, "score_breakdown": breakdown,
    }


def _b_calendar_intelligence(calendar_text: str) -> dict:
    has = bool(calendar_text) and "No upcoming events" not in calendar_text and \
        "not connected" not in calendar_text.lower() and "connect" not in calendar_text.lower()[:40]
    if has:
        head = _first_sentence(calendar_text, 200)
        score, breakdown = score_block(85, 60, 30, 95)
        return {
            "block_key": "calendar_intelligence", "title": "Calendar & Meeting Intelligence",
            "ai_summary": f"Next up: {head}",
            "evidence": [{"label": "Schedule", "value": _first_sentence(calendar_text, 120)}],
            "primary_action": chat_action("Prep me for my next meeting",
                "Prep me for my next meeting: pull up the calendar, analyze who I'm meeting and their company, "
                "find their likely weaknesses and needs, and give me exactly how to pitch and what to ask."),
            "secondary_actions": [chat_action("What's my day look like?", "Summarize my calendar for today and tomorrow and flag any conflicts.")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(30, 45, 20, 40)
    return {
        "block_key": "calendar_intelligence", "title": "Calendar & Meeting Intelligence",
        "ai_summary": "Connect Google Calendar and I'll prep you before every meeting — who they are, their weak spots, how to win.",
        "evidence": [], "primary_action": nav_action("Connect calendar", "connections"),
        "secondary_actions": [], "status": "needs_connection", "score": score, "score_breakdown": breakdown,
    }


def _b_tasks_priorities(sig: dict) -> dict:
    pending = sig.get("pending") or []
    if pending:
        top = pending[:4]
        summary = f"{len(pending)} thing{'s' if len(pending) != 1 else ''} on deck. Start with: {top[0].get('title','')}."
        evidence = [{"label": f"{i+1}", "value": a.get("title", "")} for i, a in enumerate(top)]
        urgency = 75 if len(pending) >= 3 else 55
        score, breakdown = score_block(urgency, 50, 30, _recency_from(top[0].get("created_at")))
        return {
            "block_key": "tasks_priorities", "title": "Tasks & Priorities",
            "ai_summary": summary, "evidence": evidence,
            "primary_action": chat_action("Knock out the top one",
                f"Help me do this now and take it as far as you can: {top[0].get('title','')}. {top[0].get('description','')}"),
            "secondary_actions": [nav_action("Open Morning Queue", "morning_queue")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(20, 40, 20, 35)
    return {
        "block_key": "tasks_priorities", "title": "Tasks & Priorities",
        "ai_summary": "Your queue is clear. Want me to find the highest-leverage thing to work on next?",
        "evidence": [{"label": "Queue", "value": "Empty"}],
        "primary_action": chat_action("What should I do next?", "Given everything you know about my business, what's the single highest-leverage thing I should do next?"),
        "secondary_actions": [], "status": "ok", "score": score, "score_breakdown": breakdown,
    }


def _b_ai_recommendations(sig: dict) -> dict:
    run = (sig.get("run") or [{}])[0]
    strat = run.get("strategist_output") or {}
    moves = strat.get("moves") or []
    if moves:
        top = moves[0]
        title = top.get("title") or top.get("name") or "a strategic move"
        rationale = top.get("rationale") or top.get("why") or top.get("description") or ""
        summary = f"My top recommendation: {title}. {_first_sentence(rationale, 160)}".strip()
        score, breakdown = score_block(50, 75, 30, _recency_from(run.get("completed_at") or run.get("started_at")))
        return {
            "block_key": "ai_recommendations", "title": "AI Recommendations",
            "ai_summary": summary,
            "evidence": [{"label": "Move", "value": title}],
            "primary_action": chat_action("Do this for me", f"Let's execute this recommendation. Take the first real step: {title}. {rationale}"),
            "secondary_actions": [chat_action("Why this?", f"Explain why you're recommending: {title}")],
            "status": "ok", "score": score, "score_breakdown": breakdown,
        }
    score, breakdown = score_block(30, 60, 25, 40)
    return {
        "block_key": "ai_recommendations", "title": "AI Recommendations",
        "ai_summary": "Turn on the overnight Operator and I'll wake up with a ranked set of moves to grow the business.",
        "evidence": [], "primary_action": chat_action("Give me a recommendation", "Based on everything you know, give me your single best recommendation to grow my business this week."),
        "secondary_actions": [], "status": "ok", "score": score, "score_breakdown": breakdown,
    }


async def _save_blocks(client: httpx.AsyncClient, user_id: str, run_id: str | None, blocks: list[dict]) -> int:
    """Upsert composed blocks (on user_id+block_key) so the cache always holds the latest."""
    if not blocks or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    payload = [{
        "user_id": user_id,
        "block_key": b["block_key"],
        "title": b.get("title", ""),
        "ai_summary": b.get("ai_summary", ""),
        "evidence": b.get("evidence", []),
        "primary_action": b.get("primary_action"),
        "secondary_actions": b.get("secondary_actions", []),
        "score": b.get("score", 0),
        "score_breakdown": b.get("score_breakdown", {}),
        "status": b.get("status", "ok"),
        "operator_run_id": run_id,
        "updated_at": now,
    } for b in blocks]
    try:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/business_home_blocks?on_conflict=user_id,block_key",
            headers=_write_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=payload,
            timeout=20.0,
        )
        if resp.status_code in (200, 201, 204):
            return len(payload)
        print(f"HOME_COMPOSE: save blocks status={resp.status_code} body={resp.text[:200]}")
    except Exception as e:
        print(f"HOME_COMPOSE: save blocks exception: {e}")
    return 0


def build_blocks(signals: dict, calendar_text: str, business_name: str) -> list[dict]:
    """Pure composition: signals → ordered, scored blocks. Unit-tested in isolation."""
    blocks = [
        _b_daily_briefing(signals, business_name),
        _b_highest_value_client(signals),
        _b_biggest_risk(signals),
        _b_best_lead(signals),
        _b_urgent_follow_up(signals),
        _b_pipeline_status(signals),
        _b_revenue_metrics(signals),
        _b_calendar_intelligence(calendar_text),
        _b_tasks_priorities(signals),
        _b_ai_recommendations(signals),
    ]
    # Default order is the explainable score, descending — debuggable via score_breakdown.
    blocks.sort(key=lambda b: b.get("score", 0), reverse=True)
    return blocks


async def compose_home(user_id: str, operator_run_id: str | None = None) -> dict:
    """Compose and persist this user's Home blocks. Safe to call standalone or as the
    Operator's final step. Never raises — Home composition must not fail a run."""
    if not user_id:
        return {"ok": False, "error": "user_id required"}
    try:
        async with httpx.AsyncClient() as client:
            signals = await _fetch_signals(client, user_id)
            calendar_text = await _fetch_calendar(user_id)
            user_row = (signals.get("user") or [{}])[0]
            business_name = user_row.get("company_name") or "your business"
            blocks = build_blocks(signals, calendar_text, business_name)
            saved = await _save_blocks(client, user_id, operator_run_id, blocks)
        print(f"HOME_COMPOSE: user={user_id} composed {saved} blocks")
        return {"ok": True, "blocks_saved": saved, "block_count": len(blocks)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"HOME_COMPOSE: user={user_id} failed: {e}")
        return {"ok": False, "error": str(e)[:300]}
