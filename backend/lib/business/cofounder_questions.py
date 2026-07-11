"""
Co-founder questions (Batch 72) — THE DETECTIVE's case file.

Rue doesn't act half-blind: when the strategist spots a gap the scan can't
fill, or the executor has to skip a step for missing info, the question lands
here. The owner answers in the Boardroom; answers become standing facts the
Analyst feeds into every future scan digest — so Rue literally gets
smarter about the business with every answer.

Discipline: max 3 open strategist questions (don't interrogate, investigate),
max 6 open total including executor NEEDs. Never re-ask what's on record.
"""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

MAX_OPEN_STRATEGIST = 3
MAX_OPEN_TOTAL = 6


def _headers(prefer: str | None = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


async def list_questions(user_id: str, status: str = "open", limit: int = 20) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_cofounder_questions",
                headers=_headers(),
                params={
                    "select": "*",
                    "user_id": f"eq.{user_id}",
                    "status": f"eq.{status}",
                    "order": "created_at.desc",
                    "limit": str(min(limit, 50)),
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"QUESTIONS: list failed: {e}")
    return []


async def open_counts(user_id: str) -> dict:
    """{'total': n, 'strategist': n} — drives the don't-interrogate caps."""
    rows = await list_questions(user_id, status="open", limit=50)
    return {
        "total": len(rows),
        "strategist": sum(1 for r in rows if r.get("source") == "strategist"),
    }


async def save_questions(
    user_id: str,
    questions: list[dict],
    *,
    source: str,
    operator_run_id: str | None = None,
    action_id: str | None = None,
) -> int:
    """Insert new questions, respecting the open-question caps and skipping
    near-duplicates of anything already open or answered. Returns count saved."""
    if not questions or not SUPABASE_URL or not SUPABASE_KEY:
        return 0

    counts = await open_counts(user_id)
    budget = (
        max(0, MAX_OPEN_STRATEGIST - counts["strategist"])
        if source == "strategist"
        else max(0, MAX_OPEN_TOTAL - counts["total"])
    )
    if budget <= 0:
        return 0

    # Don't re-ask: compare against everything open or already answered.
    existing = await list_questions(user_id, status="open", limit=50)
    existing += await list_questions(user_id, status="answered", limit=50)
    seen = {(q.get("question") or "").strip().lower()[:80] for q in existing}

    payload = []
    for q in questions[:budget]:
        text = (q.get("question") or "").strip()
        if not text or text.lower()[:80] in seen:
            continue
        seen.add(text.lower()[:80])
        payload.append({
            "user_id": user_id,
            "operator_run_id": operator_run_id,
            "action_id": action_id,
            "source": source,
            "question": text[:600],
            "why_it_matters": (q.get("why_it_matters") or "")[:500],
            "unlocks": (q.get("unlocks") or "")[:500],
            "status": "open",
        })
    if not payload:
        return 0

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_cofounder_questions",
                headers=_headers("return=minimal"),
                json=payload,
                timeout=15.0,
            )
        if resp.status_code in (200, 201, 204):
            return len(payload)
        print(f"QUESTIONS: save {resp.status_code}: {resp.text[:150]}")
    except Exception as e:
        print(f"QUESTIONS: save exception: {e}")
    return 0


async def resolve_question(question_id: str, user_id: str, *, answer: str | None) -> bool:
    """Answer (or dismiss when answer is None) one question, owner-scoped."""
    fields: dict = (
        {"status": "answered", "answer": answer[:2000], "answered_at": "now()"}
        if answer
        else {"status": "dismissed"}
    )
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_cofounder_questions"
                f"?id=eq.{question_id}&user_id=eq.{user_id}",
                headers=_headers("return=representation"),
                json=fields,
                timeout=10.0,
            )
        return resp.status_code == 200 and bool(resp.json())
    except Exception as e:
        print(f"QUESTIONS: resolve exception: {e}")
        return False


async def answers_digest(user_id: str, limit: int = 8) -> str:
    """The facts the owner put on record — injected into the Analyst digest."""
    rows = await list_questions(user_id, status="answered", limit=limit)
    if not rows:
        return ""
    lines = [
        f"- Q: {r.get('question','')} → A: {r.get('answer','')}"
        for r in rows if r.get("answer")
    ]
    return "\n".join(lines)
