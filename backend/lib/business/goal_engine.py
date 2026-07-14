"""Rue OS1 Goal Engine.

This is the first control-plane slice behind goal-driven execution. It keeps
the legacy Operator working while giving it durable goals, observations and an
initiative lifecycle that can survive beyond a single nightly run.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.lib.business.identity import user_id_to_uuid

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_TIMEOUT = 12.0


class GoalEngineError(RuntimeError):
    pass


class GoalConflict(GoalEngineError):
    pass


def _headers(prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _ready() -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise GoalEngineError("Supabase is not configured")


def _parse_time(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            dt = fallback
    else:
        dt = fallback
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_goal_health(goal: dict, now: datetime | None = None) -> dict:
    """Pure progress/pace calculation used by the API, Operator and tests."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    baseline = float(goal.get("baseline_value") or 0)
    current = float(goal.get("current_value") or 0)
    target = float(goal.get("target_value") or 0)
    direction = goal.get("direction") or "increase"
    start = _parse_time(goal.get("start_at"), now)
    deadline = _parse_time(goal.get("deadline"), now)

    total = max((deadline - start).total_seconds(), 1.0)
    elapsed = min(max((now - start).total_seconds() / total, 0.0), 1.0)
    span = target - baseline
    raw_progress = (current - baseline) / span if span else 0.0
    progress = min(max(raw_progress, 0.0), 1.0)
    achieved = current >= target if direction == "increase" else current <= target
    remaining_seconds = max((deadline - now).total_seconds(), 0.0)
    remaining_days = math.ceil(remaining_seconds / 86400)

    if achieved:
        health = "achieved"
    elif now >= deadline:
        health = "missed"
    else:
        pace_delta = progress - elapsed
        health = "on_track" if pace_delta >= -0.05 else ("at_risk" if pace_delta >= -0.2 else "off_track")

    remaining_value = target - current
    daily_required = remaining_value / max(remaining_seconds / 86400, 1.0)
    return {
        "progress_ratio": round(progress, 4),
        "progress_percent": round(progress * 100, 1),
        "elapsed_ratio": round(elapsed, 4),
        "pace_delta": round(progress - elapsed, 4),
        "health": health,
        "achieved": achieved,
        "remaining_value": round(remaining_value, 2),
        "remaining_days": remaining_days,
        "required_daily_change": round(daily_required, 2),
    }


async def _company_name(user_uuid: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_users",
                headers=_headers(),
                params={"select": "company_name", "user_id": f"eq.{user_uuid}", "limit": "1"},
                timeout=_TIMEOUT,
            )
        if response.status_code == 200 and response.json():
            return response.json()[0].get("company_name") or "My business"
    except Exception:
        pass
    return "My business"


async def ensure_primary_business(user_id: str) -> dict:
    """Get or lazily create the primary OS1 business and owner membership."""
    _ready()
    user_uuid = user_id_to_uuid(user_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_businesses",
            headers=_headers(),
            params={
                "select": "*",
                "owner_user_id": f"eq.{user_uuid}",
                "is_primary": "eq.true",
                "limit": "1",
            },
            timeout=_TIMEOUT,
        )
        if response.status_code == 200 and response.json():
            business = response.json()[0]
        elif response.status_code == 200:
            name = await _company_name(user_uuid)
            created = await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_businesses",
                headers=_headers("return=representation"),
                json={"owner_user_id": user_uuid, "name": name, "is_primary": True},
                timeout=_TIMEOUT,
            )
            if created.status_code not in (200, 201) or not created.json():
                raise GoalEngineError(f"Could not create OS1 business: {created.text[:180]}")
            business = created.json()[0]
        else:
            raise GoalEngineError(f"Goal Engine migration is unavailable: {response.text[:180]}")

        membership = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_business_memberships?on_conflict=business_id,user_id",
            headers=_headers("resolution=merge-duplicates,return=minimal"),
            json={"business_id": business["id"], "user_id": user_uuid, "role": "owner"},
            timeout=_TIMEOUT,
        )
        if membership.status_code not in (200, 201, 204):
            raise GoalEngineError(f"Could not establish OS1 membership: {membership.text[:180]}")
    return business


async def create_goal(user_id: str, payload: dict) -> dict:
    business = await ensure_primary_business(user_id)
    user_uuid = user_id_to_uuid(user_id)
    row = {
        "business_id": business["id"],
        "objective": payload["objective"].strip(),
        "metric_key": payload["metric_key"].strip().lower(),
        "unit": payload.get("unit") or "count",
        "direction": payload.get("direction") or "increase",
        "baseline_value": payload.get("baseline_value", 0),
        "current_value": payload.get("current_value", payload.get("baseline_value", 0)),
        "target_value": payload["target_value"],
        "deadline": payload["deadline"],
        "constraints": payload.get("constraints") or [],
        "leading_indicators": payload.get("leading_indicators") or [],
        "confidence": payload.get("confidence", 0.5),
        "created_by": user_uuid,
        "status": "active",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_goals",
            headers=_headers("return=representation"),
            json=row,
            timeout=_TIMEOUT,
        )
    if response.status_code in (200, 201) and response.json():
        goal = response.json()[0]
        goal["health"] = calculate_goal_health(goal)
        return goal
    if response.status_code == 409:
        raise GoalConflict("An active goal already exists for this metric")
    raise GoalEngineError(f"Could not create goal: {response.text[:220]}")


async def list_goals(user_id: str, status: str | None = None) -> list[dict]:
    business = await ensure_primary_business(user_id)
    params = {
        "select": "*",
        "business_id": f"eq.{business['id']}",
        "order": "status.asc,deadline.asc",
    }
    if status:
        params["status"] = f"eq.{status}"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_goals", headers=_headers(), params=params, timeout=_TIMEOUT
        )
    if response.status_code != 200:
        raise GoalEngineError(f"Could not list goals: {response.text[:180]}")
    goals = response.json()
    for goal in goals:
        goal["health"] = calculate_goal_health(goal)
    return goals


async def get_goal(user_id: str, goal_id: str) -> dict | None:
    business = await ensure_primary_business(user_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_goals",
            headers=_headers(),
            params={"select": "*", "id": f"eq.{goal_id}", "business_id": f"eq.{business['id']}", "limit": "1"},
            timeout=_TIMEOUT,
        )
    if response.status_code != 200:
        raise GoalEngineError(f"Could not load goal: {response.text[:180]}")
    if not response.json():
        return None
    goal = response.json()[0]
    goal["health"] = calculate_goal_health(goal)
    return goal


async def update_goal(user_id: str, goal_id: str, fields: dict) -> dict | None:
    existing = await get_goal(user_id, goal_id)
    if not existing:
        return None
    allowed = {
        "objective", "target_value", "deadline", "status", "confidence",
        "constraints", "leading_indicators", "current_value",
    }
    payload = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not payload:
        return existing
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_goals?id=eq.{goal_id}",
            headers=_headers("return=representation"),
            json=payload,
            timeout=_TIMEOUT,
        )
    if response.status_code in (200, 204) and response.json():
        goal = response.json()[0]
        goal["health"] = calculate_goal_health(goal)
        return goal
    raise GoalEngineError(f"Could not update goal: {response.text[:180]}")


async def record_metric_observation(
    user_id: str,
    goal_id: str,
    value: float,
    *,
    observed_at: str | None = None,
    source_type: str = "manual",
    source_ref: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict | None = None,
    metric_key: str | None = None,
) -> dict:
    goal = await get_goal(user_id, goal_id)
    if not goal:
        raise GoalEngineError("Goal not found")
    business_id = goal["business_id"]
    observed_metric_key = (metric_key or goal["metric_key"]).strip().lower()
    metric_row = {
        "business_id": business_id,
        "metric_key": observed_metric_key,
        "label": observed_metric_key.replace("_", " ").title(),
        "unit": (goal.get("unit") or "count") if observed_metric_key == goal["metric_key"] else "count",
        "source_type": source_type,
    }
    async with httpx.AsyncClient() as client:
        definition = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_metric_definitions?on_conflict=business_id,metric_key",
            headers=_headers("resolution=merge-duplicates,return=representation"),
            json=metric_row,
            timeout=_TIMEOUT,
        )
        if definition.status_code not in (200, 201) or not definition.json():
            raise GoalEngineError(f"Could not define metric: {definition.text[:180]}")
        metric_id = definition.json()[0]["id"]
        observation_payload = {
            "business_id": business_id,
            "metric_definition_id": metric_id,
            "goal_id": goal_id,
            "value": value,
            "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
            "source_type": source_type,
            "source_ref": source_ref,
            "idempotency_key": idempotency_key,
            "metadata": metadata or {},
        }
        observation = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_metric_observations",
            headers=_headers("return=representation"),
            json=observation_payload,
            timeout=_TIMEOUT,
        )
        if observation.status_code == 409 and idempotency_key:
            duplicate = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_metric_observations",
                headers=_headers(),
                params={"select": "*", "business_id": f"eq.{business_id}", "idempotency_key": f"eq.{idempotency_key}", "limit": "1"},
                timeout=_TIMEOUT,
            )
            if duplicate.status_code == 200 and duplicate.json():
                return {"observation": duplicate.json()[0], "goal": goal, "duplicate": True}
        if observation.status_code not in (200, 201) or not observation.json():
            raise GoalEngineError(f"Could not record metric: {observation.text[:180]}")

    updated = goal
    if observed_metric_key == goal["metric_key"]:
        direction = goal.get("direction") or "increase"
        achieved = value >= float(goal["target_value"]) if direction == "increase" else value <= float(goal["target_value"])
        updated = await update_goal(
            user_id,
            goal_id,
            {"current_value": value, "status": "achieved" if achieved else goal.get("status", "active")},
        )
    evaluations = await evaluate_measuring_initiatives(
        business_id,
        goal_id,
        observed_metric_key,
        value,
        observed_at=observation_payload["observed_at"],
    )
    health_event = None
    if updated and (updated.get("health") or {}).get("health") == "off_track":
        try:
            from backend.lib.business.runtime.store import emit_event

            observed_day = _parse_time(
                observation_payload["observed_at"], datetime.now(timezone.utc)
            ).date().isoformat()
            health_event = await emit_event(
                user_id,
                "goal.off_track",
                {
                    "user_id": user_id,
                    "goal_id": goal_id,
                    "health": updated["health"],
                    "notify": False,
                    "workflow_key": f"goal-replan:{goal_id}:{observed_day}",
                },
                idempotency_key=f"goal-off-track:{goal_id}:{observed_day}",
                source="measurement_engine",
                subject_type="goal",
                subject_id=goal_id,
            )
        except Exception as event_error:
            print(f"GOAL_ENGINE: off-track wake-up unavailable: {event_error}")
    return {
        "observation": observation.json()[0],
        "goal": updated,
        "evaluations": evaluations,
        "health_event": health_event,
        "duplicate": False,
    }


def _criterion_met(operator: str, actual: float, target: float) -> bool:
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    if operator == "=":
        return actual == target
    return False


async def evaluate_measuring_initiatives(
    business_id: str,
    goal_id: str,
    metric_key: str,
    value: float,
    *,
    observed_at: str,
) -> list[dict]:
    """Evaluate matching success criteria when fresh business evidence arrives."""
    # Batch 78 experiments add baseline deltas, explicit windows and honest
    # attribution confidence. Fall back to the Batch 76 evaluator during the
    # rolling migration or for legacy measuring initiatives without experiments.
    try:
        from backend.lib.business.measurement_engine import evaluate_experiments_for_observation

        enhanced = await evaluate_experiments_for_observation(business_id, goal_id, metric_key)
        if enhanced:
            return enhanced
    except Exception as exc:
        print(f"GOAL_ENGINE: enhanced measurement unavailable, using legacy evaluator: {exc}")

    evaluated: list[dict] = []
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_initiatives",
            headers=_headers(),
            params={
                "select": "id,business_id,hypothesis_id,status,success_criteria,measurement_ends_at",
                "business_id": f"eq.{business_id}",
                "goal_id": f"eq.{goal_id}",
                "status": "eq.measuring",
            },
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            return evaluated
        observation_time = _parse_time(observed_at, datetime.now(timezone.utc))
        for initiative in response.json():
            matching = [
                item for item in (initiative.get("success_criteria") or [])
                if isinstance(item, dict) and item.get("metric_key") == metric_key
            ]
            if not matching:
                continue
            results = []
            for criterion in matching:
                try:
                    met = _criterion_met(
                        str(criterion.get("operator")),
                        float(value),
                        float(criterion.get("target")),
                    )
                except (TypeError, ValueError):
                    met = False
                results.append({"criterion": criterion, "actual": value, "met": met})

            deadline = _parse_time(initiative.get("measurement_ends_at"), observation_time + timedelta(days=7))
            all_met = all(item["met"] for item in results)
            terminal_status = "succeeded" if all_met else ("failed" if observation_time >= deadline else None)
            evidence = {"metric_key": metric_key, "observed_value": value, "observed_at": observed_at, "criteria": results}
            if terminal_status:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/os1_initiatives?id=eq.{initiative['id']}",
                    headers=_headers("return=minimal"),
                    json={
                        "status": terminal_status,
                        "actual_result": evidence,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    },
                    timeout=_TIMEOUT,
                )
                await client.post(
                    f"{SUPABASE_URL}/rest/v1/os1_initiative_events",
                    headers=_headers("return=minimal"),
                    json={
                        "business_id": business_id,
                        "initiative_id": initiative["id"],
                        "event_type": "outcome_evaluated",
                        "from_status": "measuring",
                        "to_status": terminal_status,
                        "actor_type": "system",
                        "reason": "Success criteria evaluated from a metric observation.",
                        "evidence": evidence,
                        "idempotency_key": f"outcome:{metric_key}:{observed_at}",
                    },
                    timeout=_TIMEOUT,
                )
                if initiative.get("hypothesis_id"):
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/os1_hypotheses?id=eq.{initiative['hypothesis_id']}",
                        headers=_headers("return=minimal"),
                        json={"status": "supported" if terminal_status == "succeeded" else "rejected"},
                        timeout=_TIMEOUT,
                    )
            evaluated.append({"initiative_id": initiative["id"], "status": terminal_status or "measuring", "criteria": results})
    return evaluated


async def get_active_goal_snapshot(user_id: str) -> dict | None:
    goals = await list_goals(user_id, status="active")
    if not goals:
        return None
    goal = goals[0]
    business_id = goal["business_id"]
    async with httpx.AsyncClient() as client:
        bottlenecks_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_bottlenecks",
            headers=_headers(),
            params={"select": "*", "goal_id": f"eq.{goal['id']}", "status": "eq.active", "order": "severity.desc", "limit": "3"},
            timeout=_TIMEOUT,
        )
        initiatives_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_initiatives",
            headers=_headers(),
            params={"select": "id,status,title,expected_impact", "business_id": f"eq.{business_id}", "goal_id": f"eq.{goal['id']}", "order": "created_at.desc", "limit": "20"},
            timeout=_TIMEOUT,
        )
        experiments_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_experiments",
            headers=_headers(),
            params={
                "select": "id,initiative_id,status,primary_metric_key,target_value,latest_value,absolute_delta,attribution_confidence,ends_at,evaluation",
                "business_id": f"eq.{business_id}",
                "goal_id": f"eq.{goal['id']}",
                "order": "created_at.desc",
                "limit": "20",
            },
            timeout=_TIMEOUT,
        )
    bottlenecks = bottlenecks_response.json() if bottlenecks_response.status_code == 200 else []
    initiatives = initiatives_response.json() if initiatives_response.status_code == 200 else []
    experiments = experiments_response.json() if experiments_response.status_code == 200 else []
    counts: dict[str, int] = {}
    for item in initiatives:
        counts[item.get("status", "unknown")] = counts.get(item.get("status", "unknown"), 0) + 1
    return {
        "goal": goal,
        "bottlenecks": bottlenecks,
        "initiatives": initiatives,
        "initiative_counts": counts,
        "experiments": experiments,
    }


def format_goal_snapshot(snapshot: dict | None) -> str:
    if not snapshot:
        return "No structured Goal Engine goal exists yet. Use the legacy North Star as a temporary fallback."
    goal = snapshot["goal"]
    health = goal.get("health") or calculate_goal_health(goal)
    constraints = goal.get("constraints") or []
    indicators = goal.get("leading_indicators") or []
    bottlenecks = snapshot.get("bottlenecks") or []
    lines = [
        f"Objective: {goal.get('objective')}",
        f"Metric: {goal.get('metric_key')} | baseline {goal.get('baseline_value')} | current {goal.get('current_value')} | target {goal.get('target_value')} {goal.get('unit')}",
        f"Deadline: {goal.get('deadline')} | progress {health.get('progress_percent')}% | health {health.get('health')}",
        f"Required daily change: {health.get('required_daily_change')} | {health.get('remaining_days')} days remaining",
    ]
    if constraints:
        lines.append("Constraints: " + "; ".join(map(str, constraints)))
    if indicators:
        lines.append("Leading indicators: " + "; ".join(map(str, indicators)))
    if bottlenecks:
        lines.append("Active bottlenecks: " + "; ".join(f"{b.get('title')} ({b.get('evidence')})" for b in bottlenecks))
    if snapshot.get("initiative_counts"):
        lines.append("Initiative states: " + ", ".join(f"{k}={v}" for k, v in snapshot["initiative_counts"].items()))
    return "\n".join(lines)


async def persist_operator_diagnosis(
    user_id: str,
    snapshot: dict | None,
    diagnosis: dict,
) -> dict:
    """Persist the Strategist's bottleneck and causal hypothesis for this run.

    Only one bottleneck is active per goal. Repeated diagnosis of the same
    bottleneck refreshes its evidence; a changed diagnosis supersedes the old
    active constraint so the history remains inspectable.
    """
    if not snapshot or not snapshot.get("goal"):
        return {}
    goal = snapshot["goal"]
    business_id = goal["business_id"]
    bottleneck = diagnosis.get("active_bottleneck") or {}
    hypothesis = diagnosis.get("hypothesis") or {}
    title = str(bottleneck.get("title") or "").strip()
    evidence = str(bottleneck.get("evidence") or "").strip()
    if not title or not evidence:
        return {}

    async with httpx.AsyncClient() as client:
        active_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_bottlenecks",
            headers=_headers(),
            params={"select": "*", "goal_id": f"eq.{goal['id']}", "status": "eq.active", "order": "created_at.desc"},
            timeout=_TIMEOUT,
        )
        active_rows = active_response.json() if active_response.status_code == 200 else []
        matching = next((row for row in active_rows if (row.get("title") or "").strip().lower() == title.lower()), None)
        if matching:
            updated = await client.patch(
                f"{SUPABASE_URL}/rest/v1/os1_bottlenecks?id=eq.{matching['id']}",
                headers=_headers("return=representation"),
                json={
                    "evidence": evidence,
                    "severity": min(max(int(bottleneck.get("severity", 50)), 0), 100),
                    "confidence": min(max(float(bottleneck.get("confidence", 0.5)), 0), 1),
                },
                timeout=_TIMEOUT,
            )
            bottleneck_row = updated.json()[0] if updated.status_code == 200 and updated.json() else matching
        else:
            if active_rows:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/os1_bottlenecks?goal_id=eq.{goal['id']}&status=eq.active",
                    headers=_headers("return=minimal"),
                    json={"status": "superseded", "resolved_at": datetime.now(timezone.utc).isoformat()},
                    timeout=_TIMEOUT,
                )
            created = await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_bottlenecks",
                headers=_headers("return=representation"),
                json={
                    "business_id": business_id,
                    "goal_id": goal["id"],
                    "title": title,
                    "evidence": evidence,
                    "severity": min(max(int(bottleneck.get("severity", 50)), 0), 100),
                    "confidence": min(max(float(bottleneck.get("confidence", 0.5)), 0), 1),
                    "status": "active",
                    "detected_by": "operator",
                },
                timeout=_TIMEOUT,
            )
            if created.status_code not in (200, 201) or not created.json():
                raise GoalEngineError(f"Could not persist bottleneck: {created.text[:180]}")
            bottleneck_row = created.json()[0]

        hypothesis_id = None
        statement = str(hypothesis.get("statement") or "").strip()
        if statement:
            hypothesis_response = await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_hypotheses",
                headers=_headers("return=representation"),
                json={
                    "business_id": business_id,
                    "goal_id": goal["id"],
                    "bottleneck_id": bottleneck_row["id"],
                    "statement": statement,
                    "rationale": str(hypothesis.get("rationale") or ""),
                    "expected_effect": hypothesis.get("expected_effect") or {},
                    "confidence": min(max(float(hypothesis.get("confidence", 0.5)), 0), 1),
                    "status": "testing",
                },
                timeout=_TIMEOUT,
            )
            if hypothesis_response.status_code in (200, 201) and hypothesis_response.json():
                hypothesis_id = hypothesis_response.json()[0]["id"]
        return {"bottleneck_id": bottleneck_row["id"], "hypothesis_id": hypothesis_id}


async def sync_operator_initiatives(
    user_id: str,
    operator_run_id: str,
    snapshot: dict | None,
    *,
    diagnosis_refs: dict | None = None,
) -> int:
    """Dual-write legacy approval cards into the new initiative lifecycle."""
    if not snapshot or not snapshot.get("goal"):
        return 0
    goal = snapshot["goal"]
    business_id = goal["business_id"]
    async with httpx.AsyncClient() as client:
        pending = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_pending_actions",
            headers=_headers(),
            params={"select": "*", "operator_run_id": f"eq.{operator_run_id}"},
            timeout=_TIMEOUT,
        )
        if pending.status_code != 200 or not pending.json():
            return 0
        rows = []
        for action in pending.json():
            metadata = action.get("artifact_metadata") or {}
            plan = action.get("execution_plan") or metadata.get("execution_plan") or {}
            criteria = metadata.get("success_criteria") or []
            rows.append({
                "business_id": business_id,
                "goal_id": goal["id"],
                "bottleneck_id": (diagnosis_refs or {}).get("bottleneck_id"),
                "hypothesis_id": (diagnosis_refs or {}).get("hypothesis_id"),
                "operator_run_id": operator_run_id,
                "legacy_action_id": action["id"],
                "title": action.get("title") or "Untitled initiative",
                "rationale": action.get("description") or "",
                "expected_impact": action.get("expected_impact") or (action.get("artifact_metadata") or {}).get("expected_impact") or "",
                "plan": plan,
                "success_criteria": criteria,
                "risk_level": "high" if action.get("internal_or_external") == "external" else "medium",
                "status": "needs_approval",
                "priority": action.get("priority", 50),
            })
        inserted = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_initiatives?on_conflict=legacy_action_id",
            headers=_headers("resolution=merge-duplicates,return=representation"),
            json=rows,
            timeout=_TIMEOUT,
        )
    return len(inserted.json()) if inserted.status_code in (200, 201) and inserted.json() else 0


async def transition_legacy_initiative(
    legacy_action_id: str,
    to_status: str,
    *,
    reason: str = "",
    evidence: dict | None = None,
    cost_usd: float = 0,
) -> bool:
    """Mirror Executor state into the control plane and append an audit event."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            lookup = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_initiatives",
                headers=_headers(),
                params={"select": "id,business_id,status,success_criteria", "legacy_action_id": f"eq.{legacy_action_id}", "limit": "1"},
                timeout=_TIMEOUT,
            )
            if lookup.status_code != 200 or not lookup.json():
                return False
            initiative = lookup.json()[0]
            from_status = initiative.get("status")
            patch = {"status": to_status}
            if to_status == "measuring":
                measurement_start = datetime.now(timezone.utc)
                windows = [
                    int(item.get("window_days", 7))
                    for item in (initiative.get("success_criteria") or [])
                    if isinstance(item, dict)
                ]
                patch["measurement_starts_at"] = measurement_start.isoformat()
                patch["measurement_ends_at"] = (
                    measurement_start + timedelta(days=max(windows or [7]))
                ).isoformat()
            if to_status in ("completed", "succeeded", "failed", "inconclusive", "cancelled"):
                patch["completed_at"] = datetime.now(timezone.utc).isoformat()
            if evidence:
                patch["actual_result"] = evidence
            changed = await client.patch(
                f"{SUPABASE_URL}/rest/v1/os1_initiatives?id=eq.{initiative['id']}",
                headers=_headers("return=minimal"),
                json=patch,
                timeout=_TIMEOUT,
            )
            if changed.status_code not in (200, 204):
                return False
            await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_initiative_events",
                headers=_headers("return=minimal"),
                json={
                    "business_id": initiative["business_id"],
                    "initiative_id": initiative["id"],
                    "event_type": "status_changed",
                    "from_status": from_status,
                    "to_status": to_status,
                    "actor_type": "rue",
                    "reason": reason,
                    "evidence": evidence or {},
                    "cost_usd": cost_usd,
                    "idempotency_key": f"legacy:{legacy_action_id}:{to_status}",
                },
                timeout=_TIMEOUT,
            )
        if to_status == "measuring":
            try:
                from backend.lib.business.measurement_engine import start_measurement_experiment

                await start_measurement_experiment(legacy_action_id)
            except Exception as measurement_error:
                print(f"GOAL_ENGINE: measurement experiment unavailable: {measurement_error}")
        return True
    except Exception as exc:
        print(f"GOAL_ENGINE: initiative transition failed: {exc}")
        return False


async def list_initiatives(user_id: str, goal_id: str | None = None, limit: int = 30) -> list[dict]:
    business = await ensure_primary_business(user_id)
    params = {
        "select": "*",
        "business_id": f"eq.{business['id']}",
        "order": "priority.asc,created_at.desc",
        "limit": str(min(max(limit, 1), 100)),
    }
    if goal_id:
        params["goal_id"] = f"eq.{goal_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_initiatives", headers=_headers(), params=params, timeout=_TIMEOUT
        )
    if response.status_code != 200:
        raise GoalEngineError(f"Could not list initiatives: {response.text[:180]}")
    return response.json()


async def list_experiments(user_id: str, goal_id: str | None = None, limit: int = 30) -> list[dict]:
    business = await ensure_primary_business(user_id)
    params = {
        "select": "*",
        "business_id": f"eq.{business['id']}",
        "order": "created_at.desc",
        "limit": str(min(max(limit, 1), 100)),
    }
    if goal_id:
        params["goal_id"] = f"eq.{goal_id}"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_experiments",
            headers=_headers(),
            params=params,
            timeout=_TIMEOUT,
        )
    if response.status_code != 200:
        raise GoalEngineError(f"Could not list experiments: {response.text[:180]}")
    return response.json()
