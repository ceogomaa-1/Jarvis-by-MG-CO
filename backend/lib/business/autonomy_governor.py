"""Subscription, policy and quota gate for autonomous OS1 workflows."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx

from backend.lib.billing import entitlements
from backend.lib.business.identity import user_id_to_uuid

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 12.0


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


async def _capabilities(user_id: str) -> dict:
    return await asyncio.to_thread(entitlements.for_user, user_id)


async def _policy(business_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_autonomy_policies",
            headers=_headers(),
            params={"select": "*", "business_id": f"eq.{business_id}", "limit": "1"},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(f"governor migration unavailable: {response.text[:160]}")
        if response.json():
            return response.json()[0]
        created = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_autonomy_policies",
            headers=_headers("return=representation"),
            json={"business_id": business_id},
            timeout=TIMEOUT,
        )
        if created.status_code not in (200, 201) or not created.json():
            raise RuntimeError(f"could not create autonomy policy: {created.text[:160]}")
        return created.json()[0]


async def _record_nonquota_decision(workflow: dict, user_id: str, plan: str | None, decision: dict) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_autonomy_ledger?on_conflict=workflow_id",
                headers=_headers("resolution=ignore-duplicates,return=minimal"),
                json={
                    "business_id": workflow["business_id"],
                    "workflow_id": workflow["id"],
                    "user_id": user_id_to_uuid(user_id),
                    "workflow_kind": workflow.get("kind") or "unknown",
                    "plan": plan,
                    "decision": "allowed" if decision.get("allowed") else "denied",
                    "reason": decision.get("reason") or "unspecified",
                    "limits_snapshot": decision,
                },
                timeout=TIMEOUT,
            )
    except Exception as exc:
        print(f"AUTONOMY_GOVERNOR: decision ledger unavailable: {exc}")


async def _initiative_scope(workflow: dict) -> dict:
    input_data = workflow.get("input") or {}
    legacy_action_id = input_data.get("legacy_action_id")
    risk_level = "medium"
    external_actions = 0
    async with httpx.AsyncClient() as client:
        if workflow.get("initiative_id") or legacy_action_id:
            params = {"select": "risk_level"}
            if workflow.get("initiative_id"):
                params["id"] = f"eq.{workflow['initiative_id']}"
            else:
                params["legacy_action_id"] = f"eq.{legacy_action_id}"
            params["limit"] = "1"
            initiative = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_initiatives",
                headers=_headers(),
                params=params,
                timeout=TIMEOUT,
            )
            if initiative.status_code == 200 and initiative.json():
                risk_level = initiative.json()[0].get("risk_level") or risk_level
        if legacy_action_id:
            action = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_pending_actions",
                headers=_headers(),
                params={
                    "select": "internal_or_external,execution_plan",
                    "id": f"eq.{legacy_action_id}",
                    "limit": "1",
                },
                timeout=TIMEOUT,
            )
            if action.status_code == 200 and action.json():
                row = action.json()[0]
                if row.get("internal_or_external") == "external":
                    steps = (row.get("execution_plan") or {}).get("steps") or []
                    external_actions = max(len(steps), 1)
    return {"risk_level": risk_level, "external_actions": external_actions}


async def _reserve_external_actions(workflow: dict, requested: int, daily_limit: int) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/reserve_os1_external_actions",
            headers=_headers(),
            json={
                "p_business_id": workflow["business_id"],
                "p_workflow_id": workflow["id"],
                "p_usage_date": datetime.now(timezone.utc).date().isoformat(),
                "p_requested_actions": requested,
                "p_daily_limit": daily_limit,
            },
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        return {"allowed": False, "reason": f"external_capacity_reservation_failed:{response.text[:100]}"}
    return response.json() or {"allowed": False, "reason": "empty_external_capacity_decision"}


async def authorize_workflow(workflow: dict) -> dict:
    """Return an auditable allow/deny decision before any workflow side effect."""
    user_id = (workflow.get("input") or {}).get("user_id")
    business_id = workflow.get("business_id")
    if not user_id or not business_id:
        return {"allowed": False, "reason": "workflow_identity_missing"}
    if not SUPABASE_URL or not SUPABASE_KEY:
        # Local and rolling-release compatibility. Production enforcement begins
        # automatically as soon as Batch 79 is available.
        return {"allowed": True, "reason": "governor_not_configured", "fallback": True}

    try:
        policy = await _policy(business_id)
    except Exception as exc:
        if "migration unavailable" in str(exc).lower():
            return {"allowed": True, "reason": "governor_migration_unavailable", "fallback": True}
        return {"allowed": False, "reason": f"policy_unavailable:{str(exc)[:120]}"}
    if policy.get("kill_switch"):
        decision = {"allowed": False, "reason": "business_kill_switch_enabled"}
        await _record_nonquota_decision(workflow, user_id, None, decision)
        return decision

    try:
        caps = await _capabilities(user_id)
    except Exception as exc:
        return {"allowed": False, "reason": f"entitlements_unavailable:{str(exc)[:120]}"}
    if not caps.get("has_access"):
        decision = {"allowed": False, "reason": "os1_subscription_inactive", "plan": caps.get("plan")}
        await _record_nonquota_decision(workflow, user_id, caps.get("plan"), decision)
        return decision

    kind = workflow.get("kind") or "unknown"
    if kind != "operator.run":
        # Owner-approved execution is not an autonomous session, but still obeys
        # subscription access and the business-wide emergency stop above.
        if policy.get("autonomy_level") == "observe":
            decision = {"allowed": False, "reason": "policy_observe_only", "plan": caps.get("plan")}
            await _record_nonquota_decision(workflow, user_id, caps.get("plan"), decision)
            return decision
        scope = await _initiative_scope(workflow)
        allowed_risks = set(policy.get("allowed_risk_levels") or [])
        if scope["risk_level"] not in allowed_risks:
            decision = {
                "allowed": False,
                "reason": f"risk_level_not_allowed:{scope['risk_level']}",
                "plan": caps.get("plan"),
                **scope,
            }
            await _record_nonquota_decision(workflow, user_id, caps.get("plan"), decision)
            return decision
        if scope["external_actions"]:
            reservation = await _reserve_external_actions(
                workflow,
                scope["external_actions"],
                int(policy.get("max_daily_external_actions") or 0),
            )
            if not reservation.get("allowed"):
                decision = {**reservation, "plan": caps.get("plan"), **scope}
                await _record_nonquota_decision(workflow, user_id, caps.get("plan"), decision)
                return decision
        decision = {
            "allowed": True,
            "reason": "owner_approved_scope",
            "plan": caps.get("plan"),
            "max_workflow_cost_usd": float(policy.get("max_workflow_cost_usd") or 0),
            **scope,
        }
        await _record_nonquota_decision(workflow, user_id, caps.get("plan"), decision)
        return decision

    period_start = datetime.now(timezone.utc).date().replace(day=1).isoformat()
    limit = int(caps.get("autonomous_runs_monthly") or 0)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/rpc/consume_os1_autonomy_run",
            headers=_headers(),
            json={
                "p_business_id": business_id,
                "p_workflow_id": workflow["id"],
                "p_user_id": user_id_to_uuid(user_id),
                "p_workflow_kind": kind,
                "p_plan": caps.get("plan"),
                "p_period_start": period_start,
                "p_run_limit": limit,
            },
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        return {"allowed": False, "reason": f"quota_reservation_failed:{response.text[:120]}"}
    decision = response.json() or {}
    decision["plan"] = caps.get("plan")
    return decision


async def get_autonomy_status(user_id: str) -> dict:
    from backend.lib.business.goal_engine import ensure_primary_business

    business = await ensure_primary_business(user_id)
    policy = await _policy(business["id"])
    caps = await _capabilities(user_id)
    period_start = datetime.now(timezone.utc).date().replace(day=1).isoformat()
    async with httpx.AsyncClient() as client:
        usage_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_autonomy_usage",
            headers=_headers(),
            params={
                "select": "*",
                "business_id": f"eq.{business['id']}",
                "period_start": f"eq.{period_start}",
                "limit": "1",
            },
            timeout=TIMEOUT,
        )
        ledger_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_autonomy_ledger",
            headers=_headers(),
            params={
                "select": "workflow_id,workflow_kind,plan,decision,reason,limits_snapshot,created_at",
                "business_id": f"eq.{business['id']}",
                "order": "created_at.desc",
                "limit": "20",
            },
            timeout=TIMEOUT,
        )
    usage = usage_response.json()[0] if usage_response.status_code == 200 and usage_response.json() else {
        "period_start": period_start,
        "autonomous_runs": 0,
        "external_actions": 0,
        "cost_usd": 0,
    }
    monthly_limit = int(caps.get("autonomous_runs_monthly") or 0)
    return {
        "business_id": business["id"],
        "plan": caps.get("plan"),
        "has_access": caps.get("has_access"),
        "policy": policy,
        "usage": usage,
        "monthly_run_limit": monthly_limit,
        "monthly_runs_remaining": max(monthly_limit - int(usage.get("autonomous_runs") or 0), 0),
        "recent_decisions": ledger_response.json() if ledger_response.status_code == 200 else [],
    }


async def update_autonomy_policy(user_id: str, fields: dict) -> dict:
    from backend.lib.business.goal_engine import ensure_primary_business

    business = await ensure_primary_business(user_id)
    allowed = {
        "autonomy_level",
        "kill_switch",
        "max_daily_external_actions",
        "max_workflow_cost_usd",
        "allowed_risk_levels",
    }
    payload = {key: value for key, value in fields.items() if key in allowed and value is not None}
    payload["business_id"] = business["id"]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_autonomy_policies?on_conflict=business_id",
            headers=_headers("resolution=merge-duplicates,return=representation"),
            json=payload,
            timeout=TIMEOUT,
        )
    if response.status_code not in (200, 201) or not response.json():
        raise RuntimeError(f"Could not update autonomy policy: {response.text[:180]}")
    return response.json()[0]
