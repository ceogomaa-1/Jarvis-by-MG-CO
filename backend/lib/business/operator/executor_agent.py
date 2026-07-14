"""
Initiative Executor (Batch 71: Co-Founder Mode) — THE HANDS.

Before this module existed, "Ship" flipped a status field and nothing happened.
Now: when the owner approves an initiative, this agent actually executes it —
sends the emails, schedules the posts, updates the CRM, pushes the leads —
through the same tool layer the chat brain uses.

Contract:
- The owner's Approve click IS the confirmation for exactly the approved scope.
- The agent is scope-locked by prompt: it executes the approved plan, nothing
  beyond it, and reports honest receipts of every tool call.
- Cost-capped (JARVIS_EXEC_BUDGET_USD, default $0.80) and round-capped so a
  runaway loop can't burn money.
- Pre-migration safe: if the batch71 columns/status values aren't in the DB
  yet, results degrade gracefully to the legacy 'shipped' + shipped_result.
"""
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx

from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.model_router import SONNET
from backend.lib.business.tool_builder import build_tools_for_user
from backend.lib.business.tool_executor import execute_tool
from backend.lib.business.identity import user_id_to_uuid

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

MAX_ROUNDS = int(os.getenv("JARVIS_EXEC_MAX_ROUNDS", "10"))
EXEC_BUDGET_USD = float(os.getenv("JARVIS_EXEC_BUDGET_USD", "0.80"))
_CALL_TIMEOUT = 120.0
_TOOL_RESULT_CAP = 2400  # chars of tool output fed back to the model per call


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


_EXECUTOR_SYSTEM = """\
You are the EXECUTOR of Rue OS1 — the co-founder's hands.

The business owner just APPROVED one specific initiative. Your only job is to \
EXECUTE it now, for real, using the tools available to you.

THE APPROVAL CONTRACT:
- The owner's approval covers EXACTLY the approved initiative below — its \
stated plan, its stated recipients/targets, its stated content. That approval \
satisfies every confirmation requirement for those specific actions.
- You MUST NOT take any external action beyond the approved scope. No extra \
emails, no extra posts, no extra CRM writes that the plan doesn't call for.
- Reads (list, search, look up) are always allowed when needed to execute \
well (e.g. resolving a contact's email address before sending).
- If a step is impossible (missing connector, missing data), skip it, note \
why, and continue with the remaining steps. Never invent a different action \
to compensate.
- If the artifact contains placeholders like [Name] that you can resolve from \
CRM/context, resolve them. If you cannot resolve a recipient at all, do NOT \
guess an address — report the step as skipped.

QUALITY BAR: this is a real business, real recipients, real money. Execute \
like an owner: correct names, clean formatting, no test data.

WHEN FINISHED (or nothing more can be done), reply with plain text:
LINE 1: "DONE" if at least one step executed, or "FAILED" if nothing could execute.
THEN: 2-5 short lines — what actually happened, numbers included \
(e.g. "Sent intro email to sarah@x.com", "Scheduled 3 posts", "Skipped SMS — Twilio not connected").
THEN, only if a step was skipped because information ONLY THE OWNER has is \
missing, add one line per gap starting with "NEED: " — a specific question \
whose answer would let you finish next time (e.g. "NEED: What email address \
should replies to the Acme deal go to — sales@ or your personal?"). Never \
NEED something a tool lookup could answer.
No markdown headers. No apologies. Receipts only.
"""


def _initiative_prompt(action: dict) -> str:
    plan = action.get("execution_plan") or {}
    meta = action.get("artifact_metadata") or {}
    lines = [
        "APPROVED INITIATIVE — EXECUTE NOW",
        f"Title: {action.get('title','')}",
        f"Type: {action.get('action_type','')}",
        f"What it does: {action.get('description','')}",
    ]
    if action.get("expected_impact"):
        lines.append(f"Expected impact: {action['expected_impact']}")
    steps = plan.get("steps") or []
    if steps:
        lines.append("\nAPPROVED PLAN (execute these steps in order):")
        lines += [f"  {i+1}. {s}" for i, s in enumerate(steps)]
    tools = plan.get("tools") or []
    if tools:
        lines.append(f"\nExpected tools: {', '.join(tools)}")
    if meta.get("preparation_type"):
        lines.append(f"Preparation type: {meta['preparation_type']}")
    artifact = (action.get("artifact_markdown") or "").strip()
    if artifact:
        lines.append(
            "\nAPPROVED ARTIFACT (this is the content the owner approved — "
            "use it verbatim apart from resolving placeholders):\n" + artifact[:6000]
        )
    lines.append("\nExecute the initiative now. Then report receipts.")
    return "\n".join(lines)


async def _fetch_action(action_id: str) -> dict | None:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_headers(),
                params={"select": "*", "id": f"eq.{action_id}", "limit": "1"},
                timeout=10.0,
            )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"EXECUTOR: fetch_action exception: {e}")
    return None


async def _patch_action(action_id: str, fields: dict, legacy_fields: dict | None = None) -> bool:
    """PATCH the action row; on constraint/column errors retry with the legacy
    subset so everything still works before the batch71 migration is applied."""
    for payload in ([fields, legacy_fields] if legacy_fields is not None else [fields]):
        if not payload:
            continue
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/business_pending_actions?id=eq.{action_id}",
                    headers={**_headers(), "Prefer": "return=minimal"},
                    json=payload,
                    timeout=10.0,
                )
            if resp.status_code in (200, 204):
                return True
            print(f"EXECUTOR: patch {resp.status_code}: {resp.text[:180]} — payload keys {list(payload)}")
        except Exception as e:
            print(f"EXECUTOR: patch exception: {e}")
    return False


async def _notify(user_id: str, message: str, insight_type: str) -> None:
    """Drop a proactive insight so the result surfaces in-app immediately."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/business_proactive_insights",
                headers={**_headers(), "Prefer": "return=minimal"},
                json={
                    "user_id": user_id,
                    "message": message[:600],
                    "type": insight_type,
                    "is_read": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
    except Exception as e:
        print(f"EXECUTOR: notify exception: {e}")


def _parse_needs(report: str) -> list[str]:
    """Extract 'NEED: …' escalation lines from the executor's final report."""
    needs = []
    for ln in (report or "").splitlines():
        stripped = ln.strip()
        if stripped.upper().startswith("NEED:"):
            q = stripped.split(":", 1)[1].strip()
            if q:
                needs.append(q)
    return needs


def _summarize_tool_result(result_str: str) -> tuple[bool, str]:
    """(ok, short_note) from a tool's JSON result string."""
    try:
        parsed = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return True, str(result_str)[:200]
    if isinstance(parsed, dict) and parsed.get("error"):
        return False, str(parsed["error"])[:200]
    return True, json.dumps(parsed, default=str)[:200]


async def execute_initiative(
    action_id: str,
    user_id: str,
    max_budget_usd: float | None = None,
    workflow_id: str | None = None,
    business_id: str | None = None,
) -> dict:
    """Execute one approved initiative end-to-end; idempotent after success."""
    action = await _fetch_action(action_id)
    if not action:
        return {"ok": False, "error": "Initiative not found"}
    try:
        db_user_id = user_id_to_uuid(user_id)
    except ValueError:
        return {"ok": False, "error": "Invalid user identity"}
    if str(action.get("user_id")) != db_user_id:
        return {"ok": False, "error": "Initiative does not belong to this user"}
    if action.get("status") in ("executed", "shipped"):
        return {
            "ok": True,
            "already_executed": True,
            "result": action.get("execution_result") or action.get("shipped_result") or {},
        }
    if action.get("status") not in ("pending", "edited", "execution_failed"):
        return {"ok": False, "error": f"Initiative is {action.get('status')}, not approvable"}
    if not ANTHROPIC_API_KEY:
        return {"ok": False, "error": "ANTHROPIC_API_KEY not configured"}

    # Mark executing (no legacy fallback — pre-migration the status just stays
    # 'pending' while the work runs, which is harmless).
    await _patch_action(action_id, {"status": "executing"}, legacy_fields={})
    try:
        from backend.lib.business.goal_engine import transition_legacy_initiative
        await transition_legacy_initiative(
            action_id,
            "executing",
            reason="Owner approved the legacy Boardroom action.",
        )
    except Exception as e:
        print(f"EXECUTOR: control-plane executing transition failed: {e}")

    tools = await build_tools_for_user(user_id)
    usage = UsageAccumulator(SONNET)
    budget_limit = (
        min(EXEC_BUDGET_USD, max(float(max_budget_usd), 0))
        if max_budget_usd is not None
        else EXEC_BUDGET_USD
    )
    receipts: list[dict] = []
    messages: list[dict] = [{"role": "user", "content": _initiative_prompt(action)}]
    final_text = ""
    error: str | None = None

    try:
        for round_index in range(MAX_ROUNDS):
            if usage.cost()["total_usd"] >= budget_limit:
                error = f"Execution budget (${budget_limit:.2f}) reached before completion"
                break

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": SONNET,
                        "max_tokens": 2000,
                        "system": _EXECUTOR_SYSTEM,
                        "tools": tools,
                        "messages": messages,
                    },
                    timeout=_CALL_TIMEOUT,
                )
            if resp.status_code != 200:
                error = f"Anthropic API {resp.status_code}: {resp.text[:200]}"
                break

            data = resp.json()
            usage.add_sdk_usage(SimpleNamespace(**(data.get("usage") or {})))
            content = data.get("content", [])
            stop_reason = data.get("stop_reason", "")

            text_parts = [b.get("text", "") for b in content if b.get("type") == "text"]
            if text_parts:
                final_text = "\n".join(t for t in text_parts if t).strip() or final_text

            tool_blocks = [b for b in content if b.get("type") == "tool_use"]
            if stop_reason != "tool_use" or not tool_blocks:
                break  # model is done

            messages.append({"role": "assistant", "content": content})
            results_content = []
            abort_for_ambiguity = False
            for call_index, block in enumerate(tool_blocks):
                tool_name = block.get("name", "")
                tool_input = block.get("input", {}) or {}
                ledger_record = None
                ledger_mode = "legacy"
                if workflow_id and business_id:
                    try:
                        from backend.lib.business.execution_ledger import prepare_tool_execution

                        prepared = await prepare_tool_execution(
                            business_id=business_id,
                            workflow_id=workflow_id,
                            legacy_action_id=action_id,
                            round_index=round_index,
                            call_index=call_index,
                            tool_name=tool_name,
                            tool_input=tool_input,
                        )
                        ledger_mode = prepared["mode"]
                        ledger_record = prepared.get("record")
                    except Exception as ledger_error:
                        # Rolling-release fallback until Batch 80 is applied.
                        print(f"EXECUTOR: durable tool ledger unavailable: {ledger_error}")
                if ledger_mode == "replay":
                    result_str = prepared["result_text"]
                elif ledger_mode == "ambiguous":
                    result_str = json.dumps({
                        "error": "A previous external action may already have completed; automatic replay was blocked for review."
                    })
                    error = "Ambiguous prior tool side effect requires owner review"
                    abort_for_ambiguity = True
                else:
                    try:
                        result_str = await execute_tool(tool_name, tool_input, user_id)
                    except Exception as e:
                        result_str = json.dumps({"error": f"tool crashed: {e}"})
                ok, note = _summarize_tool_result(result_str)
                if ledger_record and ledger_mode == "execute":
                    try:
                        from backend.lib.business.execution_ledger import finish_tool_execution

                        await finish_tool_execution(
                            ledger_record["id"], result_str, ok=ok, error=None if ok else note
                        )
                    except Exception as ledger_error:
                        error = f"Tool ran but its durable receipt failed: {ledger_error}"
                        abort_for_ambiguity = True
                receipts.append({"tool": tool_name, "ok": ok, "note": note})
                results_content.append({
                    "type": "tool_result",
                    "tool_use_id": block.get("id", ""),
                    "content": result_str[:_TOOL_RESULT_CAP],
                })
                if abort_for_ambiguity:
                    break
            messages.append({"role": "user", "content": results_content})
            if abort_for_ambiguity:
                break
        else:
            error = f"Hit round cap ({MAX_ROUNDS}) before the model reported completion"
    except Exception as e:
        import traceback
        traceback.print_exc()
        error = f"Executor exception: {str(e)[:300]}"

    cost = usage.cost()
    executed_something = any(r["ok"] for r in receipts)
    declared_done = final_text.upper().startswith("DONE")
    declared_failed = final_text.upper().startswith("FAILED")
    success = executed_something and not declared_failed and (declared_done or error is None)

    summary = final_text or (error or "No execution report produced.")
    execution_result = {
        "summary": summary[:2000],
        "receipts": receipts[:30],
        "cost_usd": cost["total_usd"],
        "rounds": cost["rounds"],
        "error": error,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    print(
        f"EXECUTOR: action={action_id} user={user_id} success={success} "
        f"tools={len(receipts)} cost=${cost['total_usd']:.4f} err={error or '-'}"
    )

    # Detective escalation (Batch 72): steps blocked on owner-only information
    # become co-founder questions — Rue asks instead of silently giving up.
    needs = _parse_needs(final_text)
    if needs:
        try:
            from backend.lib.business.cofounder_questions import save_questions
            saved_q = await save_questions(
                user_id,
                [
                    {
                        "question": n,
                        "why_it_matters": f"Blocked a step of: {action.get('title', 'an approved initiative')}",
                        "unlocks": "Rue finishes this step the moment you answer.",
                    }
                    for n in needs if n
                ],
                source="executor",
                action_id=action_id,
            )
            if saved_q:
                print(f"EXECUTOR: raised {saved_q} question(s) from blocked steps")
        except Exception as e:
            print(f"EXECUTOR: NEED question save failed: {e}")

    now_iso = datetime.now(timezone.utc).isoformat()
    if success:
        await _patch_action(
            action_id,
            {"status": "executed", "execution_result": execution_result, "executed_at": now_iso},
            legacy_fields={"status": "shipped", "shipped_result": execution_result, "shipped_at": now_iso},
        )
        await _notify(
            user_id,
            f"✅ Executed: {action.get('title','initiative')} — {summary.splitlines()[1] if len(summary.splitlines()) > 1 else summary[:200]}",
            "initiative_executed",
        )
        try:
            from backend.lib.business.goal_engine import transition_legacy_initiative
            await transition_legacy_initiative(
                action_id,
                "measuring",
                reason="Approved execution completed; waiting for business outcome measurement.",
                evidence=execution_result,
                cost_usd=float(cost["total_usd"] or 0),
            )
        except Exception as e:
            print(f"EXECUTOR: control-plane measuring transition failed: {e}")
    else:
        await _patch_action(
            action_id,
            {"status": "execution_failed", "execution_result": execution_result},
            legacy_fields={"status": "pending", "shipped_result": execution_result},
        )
        await _notify(
            user_id,
            f"⚠️ Couldn't execute: {action.get('title','initiative')} — {(error or summary)[:220]}",
            "initiative_failed",
        )
        try:
            from backend.lib.business.goal_engine import transition_legacy_initiative
            await transition_legacy_initiative(
                action_id,
                "failed",
                reason=error or "Executor could not complete the approved plan.",
                evidence=execution_result,
                cost_usd=float(cost["total_usd"] or 0),
            )
        except Exception as e:
            print(f"EXECUTOR: control-plane failure transition failed: {e}")

    return {"ok": success, "result": execution_result}
