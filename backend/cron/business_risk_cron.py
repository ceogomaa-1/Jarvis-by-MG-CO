"""
Daily Business Risk briefing cron. Runs at 6:00 AM Toronto time.

For every user in business_user_metrics:
  1. Load their industry from business_users
  2. Evaluate flags against current metrics (Sonnet 4.6)
  3. Generate user-facing briefing (Opus 4.7)
  4. Persist to business_proactive_messages
"""
import os
from datetime import datetime, timezone

import httpx

from backend.lib.business.risk.flag_evaluator import evaluate_flags
from backend.lib.business.risk.briefing_generator import generate_briefing

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _auth_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _fetch_users_with_metrics() -> list[dict]:
    """Return list of {user_id, metrics_text, industry, company_name, first_name}."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    async with httpx.AsyncClient() as client:
        m_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_user_metrics",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "user_id,metrics_text,updated_at"},
            timeout=15.0,
        )
        if m_resp.status_code != 200:
            print(f"RISK_CRON: metrics fetch failed {m_resp.status_code}: {m_resp.text[:200]}")
            return []
        metrics_rows = m_resp.json()

    if not metrics_rows:
        return []

    user_ids = list({r["user_id"] for r in metrics_rows})
    in_filter = "(" + ",".join(f'"{uid}"' for uid in user_ids) + ")"

    async with httpx.AsyncClient() as client:
        b_resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_users",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"select": "user_id,industry,company_name", "user_id": f"in.{in_filter}"},
            timeout=15.0,
        )
        business_rows = b_resp.json() if b_resp.status_code == 200 else []

    business_by_id = {b["user_id"]: b for b in business_rows}

    combined = []
    for m in metrics_rows:
        uid = m["user_id"]
        b = business_by_id.get(uid, {})
        combined.append({
            "user_id": uid,
            "metrics_text": m.get("metrics_text", ""),
            "industry": b.get("industry", ""),
            "company_name": b.get("company_name", ""),
            "first_name": "",
        })

    return combined


async def _save_briefing(
    user_id: str,
    briefing_text: str,
    severity: str,
    summary: str,
    suggested_action: str,
    evaluator_output: dict,
) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    payload = {
        "user_id": user_id,
        "briefing_text": briefing_text,
        "flag_severity": severity,
        "flag_summary": summary,
        "suggested_action": suggested_action,
        "evaluated_flags": evaluator_output,
        "read": False,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_proactive_messages",
                headers={**_auth_headers(), "Prefer": "return=minimal"},
                json=payload,
                timeout=10.0,
            )
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        print(f"RISK_CRON: save_briefing failed for {user_id}: {e}")
        return False


async def _run_for_user(user: dict) -> bool:
    uid = user["user_id"]
    industry = user["industry"]

    if not industry:
        print(f"RISK_CRON: user {uid} has no industry — skipping")
        return False

    try:
        evaluator_output = await evaluate_flags(industry, user["metrics_text"])
        briefing = await generate_briefing(
            user["first_name"], user["company_name"], industry, evaluator_output
        )
        ok = await _save_briefing(
            user_id=uid,
            briefing_text=briefing.get("briefing_text", ""),
            severity=evaluator_output.get("overall_severity", "none"),
            summary=evaluator_output.get("summary", ""),
            suggested_action=briefing.get("suggested_action", ""),
            evaluator_output=evaluator_output,
        )
        print(f"RISK_CRON: user {uid} {'saved' if ok else 'save FAILED'} (severity={evaluator_output.get('overall_severity')})")

        # Batch 72: a RED flag is one of the two things worth interrupting the
        # owner for. notify_owner enforces the 2/day cap; dedupe is per-day so
        # a red flag never emails twice in one day.
        if ok and evaluator_output.get("overall_severity") == "red":
            try:
                from datetime import datetime, timezone
                from backend.lib.business.notify import notify_owner
                await notify_owner(
                    uid,
                    subject="🚩 Jarvis flagged a red risk in your business",
                    body_lines=[
                        evaluator_output.get("summary", "A critical risk flag was raised."),
                        briefing.get("suggested_action", "") or "Open Jarvis for the full briefing and the suggested move.",
                    ],
                    kind="risk_red_flag",
                    dedupe_key=f"risk_red_{uid}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                )
            except Exception as e:
                print(f"RISK_CRON: red-flag notify failed for {uid}: {e}")
        return ok
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"RISK_CRON: user {uid} failed: {e}")
        return False


async def run_business_risk_briefings():
    """Cron entry point. Called by APScheduler at 6:00 AM Toronto."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"RISK_CRON: Starting daily business risk briefings at {now_str}")

    users = await _fetch_users_with_metrics()
    print(f"RISK_CRON: {len(users)} users with metrics to evaluate")

    successes = 0
    for user in users:
        if await _run_for_user(user):
            successes += 1
    print(f"RISK_CRON: Done — {successes}/{len(users)} briefings saved")
