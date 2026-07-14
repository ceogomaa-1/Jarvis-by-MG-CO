"""
Operator Agent main loop. Runs the cycles per user (Batch 71: Co-Founder Mode).

CYCLE 0: Analyst (free, no LLM)    — scan the LIVE business: CRM, leads,
                                     inbox, calendar, revenue, social queue,
                                     owner decision history
CYCLE 1: Strategist (smart tier)   — pick the moves, grounded in the scan
CYCLE 2: Researcher (Sonnet + web) — back them with current data
CYCLE 3: Creator (Sonnet × N)      — produce execution-ready artifacts in parallel
CYCLE 4: Packager (smart tier)     — write approval cards WITH execution plans

When the owner approves a card, executor_agent.execute_initiative runs the
plan for real through the connector tool layer.

Budget enforcement: BudgetTracker kills the loop before any cycle that would
exceed the user's daily cap.
"""
import os

import httpx

from backend.lib.business.brand_config import get_brand_config
from backend.lib.business.connectors.registry import available_connectors_summary
from backend.lib.business.model_router import OPUS, SONNET
from backend.lib.business.operator.analyst import run_analyst
from backend.lib.business.operator.budget import BudgetTracker
from backend.lib.business.operator.strategist import run_strategist
from backend.lib.business.operator.researcher import run_researcher
from backend.lib.business.operator.creator import creator_batch_enabled, run_creator
from backend.lib.business.operator.packager import run_packager
from backend.lib.business.operator.home_composer import compose_home
from backend.lib.business.goal_engine import (
    format_goal_snapshot,
    get_active_goal_snapshot,
    persist_operator_diagnosis,
    sync_operator_initiatives,
)
from backend.lib.business.identity import user_id_to_uuid

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


async def _create_run_row(user_id: str) -> str | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_operator_runs",
                headers={**_headers(), "Prefer": "return=representation"},
                json={"user_id": user_id_to_uuid(user_id), "status": "running"},
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            data = resp.json()
            return (data[0] if isinstance(data, list) else data).get("id")
    except Exception as e:
        print(f"OPERATOR: create_run_row exception: {e}")
    return None


async def _patch_run_row(run_id: str, fields: dict) -> None:
    if not run_id or not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/business_operator_runs?id=eq.{run_id}",
                headers={**_headers(), "Prefer": "return=minimal"},
                json=fields,
                timeout=10.0,
            )
    except Exception as e:
        print(f"OPERATOR: patch_run_row exception: {e}")


def _card_row(user_id: str, run_id: str, c: dict, *, legacy: bool) -> dict:
    row = {
        "user_id": user_id_to_uuid(user_id),
        "operator_run_id": run_id,
        "action_type": c.get("action_type", "report"),
        "title": c.get("title", "Untitled"),
        "description": c.get("description", ""),
        "internal_or_external": c.get("internal_or_external", "internal"),
        "artifact_markdown": c.get("artifact_markdown", ""),
        "artifact_metadata": {
            "move_id": c.get("move_id"),
            "preparation_type": c.get("preparation_type", ""),
            # Mirror the plan into metadata too so pre-migration rows keep it.
            "execution_plan": c.get("execution_plan") or {},
            "expected_impact": c.get("expected_impact", ""),
            "success_criteria": c.get("success_criteria") or [],
        },
        "connector_type": c.get("connector_type") or None,
        "priority": c.get("priority", 50),
    }
    if not legacy:
        row["execution_plan"] = c.get("execution_plan") or {}
        row["expected_impact"] = c.get("expected_impact", "")
    return row


async def _save_pending_actions(user_id: str, run_id: str, cards: list[dict]) -> int:
    """Bulk-insert cards into business_pending_actions. Returns count saved.

    Tries the batch71 shape (execution_plan / expected_impact columns) first;
    if the migration hasn't been applied yet, falls back to the legacy shape
    (the plan still rides along inside artifact_metadata)."""
    if not cards or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    for legacy in (False, True):
        payload = [_card_row(user_id, run_id, c, legacy=legacy) for c in cards]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                    headers={**_headers(), "Prefer": "return=minimal"},
                    json=payload,
                    timeout=20.0,
                )
            if resp.status_code in (200, 201, 204):
                return len(payload)
            print(f"OPERATOR: save_pending_actions {resp.status_code} (legacy={legacy}): {resp.text[:150]}")
        except Exception as e:
            print(f"OPERATOR: save_pending_actions exception (legacy={legacy}): {e}")
    return 0


async def _fetch_user_context(user_id: str) -> dict:
    """Pull industry, latest metrics, latest flags for the run."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    out = {"industry": "", "metrics_text": "", "flags_summary": "", "company_name": ""}
    try:
        db_user_id = user_id_to_uuid(user_id)
    except ValueError:
        return out
    read_h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            bu = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_users",
                headers=read_h,
                params={"select": "industry,company_name", "user_id": f"eq.{db_user_id}", "limit": "1"},
                timeout=10.0,
            )
            if bu.status_code == 200 and bu.json():
                row = bu.json()[0]
                out["industry"] = row.get("industry", "")
                out["company_name"] = row.get("company_name", "")

            m = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_metrics",
                headers=read_h,
                params={"select": "metrics_text", "user_id": f"eq.{db_user_id}", "limit": "1"},
                timeout=10.0,
            )
            if m.status_code == 200 and m.json():
                out["metrics_text"] = m.json()[0].get("metrics_text", "")

            f = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_proactive_messages",
                headers=read_h,
                params={
                    "select": "flag_summary,flag_severity",
                    "user_id": f"eq.{db_user_id}",
                    "order": "created_at.desc",
                    "limit": "1",
                },
                timeout=10.0,
            )
            if f.status_code == 200 and f.json():
                row = f.json()[0]
                out["flags_summary"] = f"{row.get('flag_severity','none')}: {row.get('flag_summary','')}"
    except Exception as e:
        print(f"OPERATOR: fetch_user_context exception: {e}")
    return out


async def create_operator_run_row(user_id: str) -> str | None:
    """Public entry point for callers that need to create the row before launching the pipeline."""
    return await _create_run_row(user_id)


async def run_operator_for_user(
    user_id: str,
    existing_run_id: str | None = None,
    notify: bool = False,
) -> dict:
    """Execute the full 4-cycle operator run for one user.

    Pass existing_run_id when the caller has already created the run row (e.g. for
    background-task launches that need to return the run_id immediately).

    notify=True (cron runs only) sends the owner the morning brief through the
    capped notifier — user-triggered runs skip it because the owner is watching
    the takeover live in the app.
    """
    print(f"OPERATOR: Starting run for user {user_id}")

    brand = await get_brand_config(user_id)
    budget = BudgetTracker(daily_budget_usd=brand.get("operator_daily_budget_usd", 5.0))
    run_id = existing_run_id or await _create_run_row(user_id)
    if not run_id:
        return {"error": "Could not create run row"}

    user_ctx = await _fetch_user_context(user_id)
    connector_summary = await available_connectors_summary(user_id)

    # Batch 76: a structured goal is now the Operator's control plane. This is
    # deliberately fail-soft during rollout: if the migration is not applied or
    # the owner has not configured a goal, the legacy North Star still works.
    goal_snapshot = None
    try:
        goal_snapshot = await get_active_goal_snapshot(user_id)
    except Exception as e:
        print(f"OPERATOR: structured goal unavailable for {user_id}: {e}")

    business_name = brand.get("display_name") or user_ctx.get("company_name") or "the business"
    structured_goal = (goal_snapshot or {}).get("goal") or {}
    north_star_label = structured_goal.get("objective") or brand.get("north_star_target_label") or "$1M ARR"
    north_star_usd = structured_goal.get("target_value") or brand.get("north_star_target_usd") or 1_000_000
    industry = user_ctx.get("industry", "")

    base_user_ctx = {
        "display_name": business_name,
        "industry": industry,
        "north_star_label": north_star_label,
        "north_star_usd": north_star_usd,
        "goal_context": format_goal_snapshot(goal_snapshot),
    }

    cycles_completed = 0

    try:
        # ─── CYCLE 0: ANALYST (free — no LLM) ─────────────────────
        # The co-founder's walk through the live business before proposing
        # anything. Fail-soft: a dead scan just means a thinner digest.
        scan_digest = ""
        try:
            snapshot = await run_analyst(user_id)
            scan_digest = snapshot.get("digest", "")
            # Separate patch: the snapshot column ships in batch71 — if the
            # migration isn't applied yet this 400s harmlessly on its own.
            await _patch_run_row(run_id, {"snapshot": snapshot})
            print(f"OPERATOR: analyst scanned {snapshot.get('sources_ok')} for {user_id}")
        except Exception as e:
            print(f"OPERATOR: analyst failed for {user_id}: {e}")

        # ─── CYCLE 1: STRATEGIST ──────────────────────────────────
        if not budget.can_afford(OPUS, input_tokens_est=2500, max_output_tokens=3000):
            await _patch_run_row(run_id, {
                "status": "budget_capped",
                "error": "Daily budget exhausted before Strategist",
                "completed_at": "now()",
            })
            return {"status": "budget_capped", "cycles_completed": 0}

        budget.charge(OPUS, input_tokens_est=2500, max_output_tokens=3000)
        strategist_plan = await run_strategist(
            user_context=base_user_ctx,
            industry_briefing="",
            latest_metrics=user_ctx.get("metrics_text", ""),
            latest_flags_summary=user_ctx.get("flags_summary", ""),
            business_scan_digest=scan_digest,
            connector_summary=connector_summary,
        )
        cycles_completed = 1
        await _patch_run_row(run_id, {
            "cycles_completed": 1,
            "strategist_output": strategist_plan,
            "total_cost_usd": round(budget.spent_usd, 4),
        })

        # Detective questions (Batch 72): persist the strategist's 0-3 gap
        # questions. save_questions enforces the open-question caps + dedupe.
        questions_saved = 0
        if strategist_plan.get("questions"):
            try:
                from backend.lib.business.cofounder_questions import save_questions
                questions_saved = await save_questions(
                    user_id,
                    strategist_plan["questions"],
                    source="strategist",
                    operator_run_id=run_id,
                )
                if questions_saved:
                    print(f"OPERATOR: detective raised {questions_saved} question(s) for {user_id}")
            except Exception as e:
                print(f"OPERATOR: question save failed for {user_id}: {e}")

        if strategist_plan.get("error") or not strategist_plan.get("moves"):
            await _patch_run_row(run_id, {
                "status": "failed",
                "error": strategist_plan.get("error", "Strategist produced no moves"),
                "completed_at": "now()",
            })
            return {"status": "failed", "cycles_completed": 1}

        diagnosis_refs = {}
        try:
            diagnosis_refs = await persist_operator_diagnosis(
                user_id,
                goal_snapshot,
                strategist_plan.get("goal_diagnosis") or {},
            )
        except Exception as e:
            print(f"OPERATOR: diagnosis persistence failed for {user_id}: {e}")

        # ─── CYCLE 2: RESEARCHER ──────────────────────────────────
        if budget.can_afford(SONNET, input_tokens_est=2000, max_output_tokens=3000):
            budget.charge(SONNET, input_tokens_est=2000, max_output_tokens=3000)
            researcher_output = await run_researcher(strategist_plan, industry)
        else:
            researcher_output = {"research": {}, "skipped": "budget"}
        cycles_completed = 2
        await _patch_run_row(run_id, {
            "cycles_completed": 2,
            "researcher_output": researcher_output,
            "total_cost_usd": round(budget.spent_usd, 4),
        })

        # ─── CYCLE 3: CREATOR (parallel sub-agents) ───────────────
        moves_to_create = strategist_plan.get("moves", [])[:6]
        creator_cost_multiplier = 0.5 if creator_batch_enabled(len(moves_to_create)) else 1.0
        affordable_count = 0
        for _ in moves_to_create:
            if budget.can_afford(
                SONNET,
                input_tokens_est=2000,
                max_output_tokens=2500,
                multiplier=creator_cost_multiplier,
            ):
                budget.charge(
                    SONNET,
                    input_tokens_est=2000,
                    max_output_tokens=2500,
                    multiplier=creator_cost_multiplier,
                )
                affordable_count += 1
            else:
                break
        moves_to_create = moves_to_create[:affordable_count]
        truncated_plan = {**strategist_plan, "moves": moves_to_create}

        if moves_to_create:
            creator_outputs = await run_creator(
                strategist_plan=truncated_plan,
                researcher_output=researcher_output,
                industry=industry,
                business_name=business_name,
                north_star_label=north_star_label,
                connector_summary=connector_summary,
                max_parallel=len(moves_to_create),
                scan_digest=scan_digest,
            )
        else:
            creator_outputs = []
        cycles_completed = 3
        await _patch_run_row(run_id, {
            "cycles_completed": 3,
            "creator_outputs": creator_outputs,
            "total_cost_usd": round(budget.spent_usd, 4),
        })

        # ─── CYCLE 4: PACKAGER ────────────────────────────────────
        if budget.can_afford(OPUS, input_tokens_est=3500, max_output_tokens=4000):
            budget.charge(OPUS, input_tokens_est=3500, max_output_tokens=4000)
            packager_output = await run_packager(
                strategist_plan=strategist_plan,
                creator_outputs=creator_outputs,
                business_name=business_name,
                north_star_label=north_star_label,
                connector_summary=connector_summary,
            )
        else:
            # Budget capped — auto-package without the smart tier
            packager_output = {
                "morning_message": "Operator ran overnight. Budget capped before Packager — raw artifacts queued for review.",
                "cards": [
                    {
                        "move_id": c.get("move_id"),
                        "action_type": c.get("preparation_type", "report"),
                        "internal_or_external": "internal",
                        "title": c.get("title", "Untitled artifact"),
                        "description": "",
                        "priority": 50,
                        "connector_type": "",
                        "artifact_markdown": c.get("artifact", ""),
                        "execution_plan": {"mode": "manual", "steps": [], "tools": []},
                        "expected_impact": "",
                    }
                    for c in creator_outputs if c.get("ok")
                ],
            }
        cycles_completed = 4

        cards = packager_output.get("cards", [])
        actions_saved = await _save_pending_actions(user_id, run_id, cards)

        # Dual-write approval cards into the durable initiative lifecycle. The
        # legacy Boardroom remains the execution UI until its migration is done.
        initiatives_synced = 0
        try:
            initiatives_synced = await sync_operator_initiatives(
                user_id, run_id, goal_snapshot, diagnosis_refs=diagnosis_refs
            )
        except Exception as e:
            print(f"OPERATOR: initiative control-plane sync failed for {user_id}: {e}")

        await _patch_run_row(run_id, {
            "cycles_completed": 4,
            "packager_output": packager_output,
            "status": "complete",
            "total_cost_usd": round(budget.spent_usd, 4),
            "completed_at": "now()",
        })

        # ─── FINAL STEP: COMPOSE HOME ─────────────────────────────
        # Batch 67: roll everything this run produced — plus the user's standing
        # signals (risk flags, metrics, leads, calendar) — into the precomputed Home
        # block cache so the Home view renders instantly. Never fails the run.
        try:
            await compose_home(user_id, run_id)
        except Exception as e:
            print(f"OPERATOR: compose_home failed for {user_id}: {e}")

        # ─── MORNING BRIEF (Batch 72, cron runs only) ─────────────
        # One respectful notification: what the co-founder prepared overnight.
        # notify_owner enforces the 2/day cap + dedupe, so this can never spam.
        if notify and actions_saved:
            try:
                from backend.lib.business.notify import notify_owner
                auto_count = sum(
                    1 for c in cards if (c.get("execution_plan") or {}).get("mode") == "auto"
                )
                body_lines = [
                    packager_output.get("morning_message", "")
                    or f"Rue prepared {actions_saved} initiatives overnight.",
                    f"{actions_saved} initiative(s) are waiting in the Boardroom"
                    + (f" — {auto_count} execute the moment you approve." if auto_count else "."),
                ]
                if questions_saved:
                    body_lines.append(
                        f"Rue also has {questions_saved} question(s) for you — "
                        "answering them sharpens the next plan."
                    )
                await notify_owner(
                    user_id,
                    subject=f"Your co-founder prepared {actions_saved} moves — they need your green light",
                    body_lines=[l for l in body_lines if l],
                    kind="morning_brief",
                    dedupe_key=f"run_{run_id}",
                )
            except Exception as e:
                print(f"OPERATOR: morning brief notify failed for {user_id}: {e}")

        print(
            f"OPERATOR: Run complete for {user_id}. "
            f"{actions_saved} actions queued. Cost: ${budget.spent_usd:.4f}"
        )
        return {
            "status": "complete",
            "cycles_completed": 4,
            "actions_queued": actions_saved,
            "initiatives_synced": initiatives_synced,
            "questions_raised": questions_saved,
            "total_cost_usd": round(budget.spent_usd, 4),
            "morning_message": packager_output.get("morning_message", ""),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"OPERATOR: unhandled exception for user {user_id}: {e}")
        await _patch_run_row(run_id, {
            "status": "failed",
            "error": str(e)[:500],
            "cycles_completed": cycles_completed,
            "total_cost_usd": round(budget.spent_usd, 4),
            "completed_at": "now()",
        })
        return {"status": "failed", "error": str(e), "cycles_completed": cycles_completed}
