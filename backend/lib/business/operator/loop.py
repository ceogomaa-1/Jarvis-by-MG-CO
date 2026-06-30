"""
Operator Agent main loop. Runs the 4 cycles per user.

CYCLE 1: Strategist (Opus)         — pick the moves
CYCLE 2: Researcher (Sonnet + web) — back them with current data
CYCLE 3: Creator (Sonnet × N)      — produce the artifacts in parallel
CYCLE 4: Packager (Opus)           — write the morning approval cards

Budget enforcement: BudgetTracker kills the loop before any cycle that would
exceed the user's daily cap.
"""
import os

import httpx

from backend.lib.business.brand_config import get_brand_config
from backend.lib.business.connectors.registry import available_connectors_summary
from backend.lib.business.operator.budget import BudgetTracker
from backend.lib.business.operator.strategist import run_strategist
from backend.lib.business.operator.researcher import run_researcher
from backend.lib.business.operator.creator import creator_batch_enabled, run_creator
from backend.lib.business.operator.packager import run_packager
from backend.lib.business.operator.home_composer import compose_home

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
                json={"user_id": user_id, "status": "running"},
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


async def _save_pending_actions(user_id: str, run_id: str, cards: list[dict]) -> int:
    """Bulk-insert cards into business_pending_actions. Returns count saved."""
    if not cards or not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    payload = [
        {
            "user_id": user_id,
            "operator_run_id": run_id,
            "action_type": c.get("action_type", "report"),
            "title": c.get("title", "Untitled"),
            "description": c.get("description", ""),
            "internal_or_external": c.get("internal_or_external", "internal"),
            "artifact_markdown": c.get("artifact_markdown", ""),
            "artifact_metadata": {
                "move_id": c.get("move_id"),
                "preparation_type": c.get("preparation_type", ""),
            },
            "connector_type": c.get("connector_type") or None,
            "priority": c.get("priority", 50),
        }
        for c in cards
    ]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers={**_headers(), "Prefer": "return=minimal"},
                json=payload,
                timeout=20.0,
            )
        return len(payload) if resp.status_code in (200, 201, 204) else 0
    except Exception as e:
        print(f"OPERATOR: save_pending_actions exception: {e}")
        return 0


async def _fetch_user_context(user_id: str) -> dict:
    """Pull industry, latest metrics, latest flags for the run."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}
    out = {"industry": "", "metrics_text": "", "flags_summary": "", "company_name": ""}
    read_h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            bu = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_users",
                headers=read_h,
                params={"select": "industry,company_name", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
            if bu.status_code == 200 and bu.json():
                row = bu.json()[0]
                out["industry"] = row.get("industry", "")
                out["company_name"] = row.get("company_name", "")

            m = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_metrics",
                headers=read_h,
                params={"select": "metrics_text", "user_id": f"eq.{user_id}", "limit": "1"},
                timeout=10.0,
            )
            if m.status_code == 200 and m.json():
                out["metrics_text"] = m.json()[0].get("metrics_text", "")

            f = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_proactive_messages",
                headers=read_h,
                params={
                    "select": "flag_summary,flag_severity",
                    "user_id": f"eq.{user_id}",
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


async def run_operator_for_user(user_id: str, existing_run_id: str | None = None) -> dict:
    """Execute the full 4-cycle operator run for one user.

    Pass existing_run_id when the caller has already created the run row (e.g. for
    background-task launches that need to return the run_id immediately).
    """
    print(f"OPERATOR: Starting run for user {user_id}")

    brand = await get_brand_config(user_id)
    budget = BudgetTracker(daily_budget_usd=brand.get("operator_daily_budget_usd", 5.0))
    run_id = existing_run_id or await _create_run_row(user_id)
    if not run_id:
        return {"error": "Could not create run row"}

    user_ctx = await _fetch_user_context(user_id)
    connector_summary = await available_connectors_summary(user_id)

    business_name = brand.get("display_name") or user_ctx.get("company_name") or "the business"
    north_star_label = brand.get("north_star_target_label") or "$1M ARR"
    north_star_usd = brand.get("north_star_target_usd") or 1_000_000
    industry = user_ctx.get("industry", "")

    base_user_ctx = {
        "display_name": business_name,
        "industry": industry,
        "north_star_label": north_star_label,
        "north_star_usd": north_star_usd,
    }

    cycles_completed = 0

    try:
        # ─── CYCLE 1: STRATEGIST ──────────────────────────────────
        if not budget.can_afford("claude-opus-4-7", input_tokens_est=1500, max_output_tokens=2048):
            await _patch_run_row(run_id, {
                "status": "budget_capped",
                "error": "Daily budget exhausted before Strategist",
                "completed_at": "now()",
            })
            return {"status": "budget_capped", "cycles_completed": 0}

        budget.charge("claude-opus-4-7", input_tokens_est=1500, max_output_tokens=2048)
        strategist_plan = await run_strategist(
            user_context=base_user_ctx,
            industry_briefing="",
            latest_metrics=user_ctx.get("metrics_text", ""),
            latest_flags_summary=user_ctx.get("flags_summary", ""),
        )
        cycles_completed = 1
        await _patch_run_row(run_id, {
            "cycles_completed": 1,
            "strategist_output": strategist_plan,
            "total_cost_usd": round(budget.spent_usd, 4),
        })

        if strategist_plan.get("error") or not strategist_plan.get("moves"):
            await _patch_run_row(run_id, {
                "status": "failed",
                "error": strategist_plan.get("error", "Strategist produced no moves"),
                "completed_at": "now()",
            })
            return {"status": "failed", "cycles_completed": 1}

        # ─── CYCLE 2: RESEARCHER ──────────────────────────────────
        if budget.can_afford("claude-sonnet-4-6", input_tokens_est=2000, max_output_tokens=3000):
            budget.charge("claude-sonnet-4-6", input_tokens_est=2000, max_output_tokens=3000)
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
                "claude-sonnet-4-6",
                input_tokens_est=2000,
                max_output_tokens=2500,
                multiplier=creator_cost_multiplier,
            ):
                budget.charge(
                    "claude-sonnet-4-6",
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
        if budget.can_afford("claude-opus-4-7", input_tokens_est=3000, max_output_tokens=3000):
            budget.charge("claude-opus-4-7", input_tokens_est=3000, max_output_tokens=3000)
            packager_output = await run_packager(
                strategist_plan=strategist_plan,
                creator_outputs=creator_outputs,
                business_name=business_name,
                north_star_label=north_star_label,
            )
        else:
            # Budget capped — auto-package without Opus
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
                    }
                    for c in creator_outputs if c.get("ok")
                ],
            }
        cycles_completed = 4

        cards = packager_output.get("cards", [])
        actions_saved = await _save_pending_actions(user_id, run_id, cards)

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

        print(
            f"OPERATOR: Run complete for {user_id}. "
            f"{actions_saved} actions queued. Cost: ${budget.spent_usd:.4f}"
        )
        return {
            "status": "complete",
            "cycles_completed": 4,
            "actions_queued": actions_saved,
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
