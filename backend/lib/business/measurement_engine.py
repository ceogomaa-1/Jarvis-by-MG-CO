"""Outcome measurement for Rue OS1 initiatives.

The engine is intentionally conservative: it proves target movement and stores
an attribution confidence score, but never claims that correlation is causation.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TIMEOUT = 15.0


class MeasurementUnavailable(RuntimeError):
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
        raise MeasurementUnavailable("Supabase is not configured")


def _time(value: Any, fallback: datetime | None = None) -> datetime:
    fallback = fallback or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _meets(operator: str, actual: float, target: float) -> bool:
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    if operator == "=":
        return actual == target
    return False


def evaluate_measurement(
    experiment: dict,
    observations: list[dict],
    *,
    now: datetime | None = None,
) -> dict:
    """Pure, deterministic evaluation used by workers and tests."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    starts_at = _time(experiment.get("starts_at"), now)
    ends_at = _time(experiment.get("ends_at"), starts_at + timedelta(days=7))
    evidence_cutoff = min(now, ends_at)
    usable = sorted(
        (
            item for item in observations
            if starts_at <= _time(item.get("observed_at"), starts_at) <= evidence_cutoff
        ),
        key=lambda item: _time(item.get("observed_at"), starts_at),
    )
    baseline_raw = experiment.get("baseline_value")
    baseline = float(baseline_raw) if baseline_raw is not None else None
    latest = float(usable[-1]["value"]) if usable else None
    target = float(experiment.get("target_value") or 0)
    operator = str(experiment.get("target_operator") or ">=")
    window_closed = now >= ends_at

    if latest is None:
        status = "inconclusive" if window_closed else "running"
        delta = relative_delta = None
        confidence = 0.0
        target_met = False
    else:
        target_met = _meets(operator, latest, target)
        status = "won" if target_met else ("lost" if window_closed else "running")
        delta = latest - baseline if baseline is not None else None
        relative_delta = delta / abs(baseline) if delta is not None and baseline else None
        confidence = min(0.35 + 0.08 * min(len(usable), 5), 0.75)
        if baseline is None:
            confidence = min(confidence, 0.3)

    return {
        "status": status,
        "target_met": target_met,
        "target_operator": operator,
        "target_value": target,
        "baseline_value": baseline,
        "latest_value": latest,
        "absolute_delta": round(delta, 4) if delta is not None else None,
        "relative_delta": round(relative_delta, 6) if relative_delta is not None else None,
        "sample_count": len(usable),
        "window_closed": window_closed,
        "attribution_confidence": round(confidence, 2),
        "attribution_note": (
            "Target movement is measured; causal attribution remains probabilistic without a control group."
        ),
        "evaluated_at": now.isoformat(),
    }


def _criterion(initiative: dict, goal: dict) -> dict:
    criteria = [item for item in (initiative.get("success_criteria") or []) if isinstance(item, dict)]
    valid = next(
        (
            item for item in criteria
            if item.get("metric_key") and item.get("operator") in {">=", "<=", "="}
            and item.get("target") is not None
        ),
        None,
    )
    if valid:
        return valid
    return {
        "metric_key": goal["metric_key"],
        "operator": ">=" if goal.get("direction", "increase") == "increase" else "<=",
        "target": goal["target_value"],
        "window_days": 7,
    }


async def start_measurement_experiment(legacy_action_id: str) -> dict | None:
    """Snapshot the baseline when execution enters its measurement window."""
    _ready()
    async with httpx.AsyncClient() as client:
        initiative_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_initiatives",
            headers=_headers(),
            params={"select": "*", "legacy_action_id": f"eq.{legacy_action_id}", "limit": "1"},
            timeout=TIMEOUT,
        )
        if initiative_response.status_code != 200 or not initiative_response.json():
            return None
        initiative = initiative_response.json()[0]
        goal_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_goals",
            headers=_headers(),
            params={"select": "*", "id": f"eq.{initiative['goal_id']}", "limit": "1"},
            timeout=TIMEOUT,
        )
        if goal_response.status_code != 200 or not goal_response.json():
            return None
        goal = goal_response.json()[0]
        criterion = _criterion(initiative, goal)
        starts_at = _time(initiative.get("measurement_starts_at"))
        ends_at = _time(
            initiative.get("measurement_ends_at"),
            starts_at + timedelta(days=max(int(criterion.get("window_days", 7)), 1)),
        )

        definition_response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_metric_definitions",
            headers=_headers(),
            params={
                "select": "id",
                "business_id": f"eq.{initiative['business_id']}",
                "metric_key": f"eq.{criterion['metric_key']}",
                "limit": "1",
            },
            timeout=TIMEOUT,
        )
        baseline_value = None
        baseline_observed_at = None
        if definition_response.status_code == 200 and definition_response.json():
            metric_id = definition_response.json()[0]["id"]
            baseline_response = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_metric_observations",
                headers=_headers(),
                params={
                    "select": "value,observed_at",
                    "metric_definition_id": f"eq.{metric_id}",
                    "observed_at": f"lte.{starts_at.isoformat()}",
                    "order": "observed_at.desc",
                    "limit": "1",
                },
                timeout=TIMEOUT,
            )
            if baseline_response.status_code == 200 and baseline_response.json():
                baseline_value = baseline_response.json()[0].get("value")
                baseline_observed_at = baseline_response.json()[0].get("observed_at")
        if baseline_value is None and criterion["metric_key"] == goal.get("metric_key"):
            baseline_value = goal.get("current_value")
            baseline_observed_at = starts_at.isoformat()

        row = {
            "business_id": initiative["business_id"],
            "goal_id": initiative["goal_id"],
            "initiative_id": initiative["id"],
            "hypothesis_id": initiative.get("hypothesis_id"),
            "primary_metric_key": criterion["metric_key"],
            "target_operator": criterion["operator"],
            "target_value": criterion["target"],
            "baseline_value": baseline_value,
            "baseline_observed_at": baseline_observed_at,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "status": "running",
        }
        experiment_response = await client.post(
            f"{SUPABASE_URL}/rest/v1/os1_experiments?on_conflict=initiative_id",
            headers=_headers("resolution=merge-duplicates,return=representation"),
            json=row,
            timeout=TIMEOUT,
        )
        if experiment_response.status_code not in (200, 201) or not experiment_response.json():
            raise MeasurementUnavailable(f"Could not start experiment: {experiment_response.text[:180]}")
        experiment = experiment_response.json()[0]
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_initiatives?id=eq.{initiative['id']}",
            headers=_headers("return=minimal"),
            json={
                "baseline_snapshot": {
                    "metric_key": criterion["metric_key"],
                    "value": baseline_value,
                    "observed_at": baseline_observed_at,
                }
            },
            timeout=TIMEOUT,
        )
    return experiment


async def _observations_for_experiment(client: httpx.AsyncClient, experiment: dict) -> list[dict]:
    definition = await client.get(
        f"{SUPABASE_URL}/rest/v1/os1_metric_definitions",
        headers=_headers(),
        params={
            "select": "id",
            "business_id": f"eq.{experiment['business_id']}",
            "metric_key": f"eq.{experiment['primary_metric_key']}",
            "limit": "1",
        },
        timeout=TIMEOUT,
    )
    if definition.status_code != 200 or not definition.json():
        return []
    response = await client.get(
        f"{SUPABASE_URL}/rest/v1/os1_metric_observations",
        headers=_headers(),
        params={
            "select": "value,observed_at,source_type,source_ref,metadata",
            "metric_definition_id": f"eq.{definition.json()[0]['id']}",
            "observed_at": f"gte.{experiment['starts_at']}",
            "order": "observed_at.asc",
            "limit": "500",
        },
        timeout=TIMEOUT,
    )
    return response.json() if response.status_code == 200 else []


async def evaluate_experiment(experiment: dict, *, now: datetime | None = None) -> dict:
    _ready()
    async with httpx.AsyncClient() as client:
        observations = await _observations_for_experiment(client, experiment)
        result = evaluate_measurement(experiment, observations, now=now)
        terminal = result["status"] in {"won", "lost", "inconclusive"}
        patch = {
            "status": result["status"],
            "latest_value": result["latest_value"],
            "absolute_delta": result["absolute_delta"],
            "relative_delta": result["relative_delta"],
            "sample_count": result["sample_count"],
            "attribution_confidence": result["attribution_confidence"],
            "evaluation": result,
            "evaluated_at": result["evaluated_at"],
        }
        updated = await client.patch(
            f"{SUPABASE_URL}/rest/v1/os1_experiments?id=eq.{experiment['id']}",
            headers=_headers("return=representation"),
            json=patch,
            timeout=TIMEOUT,
        )
        if updated.status_code != 200 or not updated.json():
            raise MeasurementUnavailable(f"Could not evaluate experiment: {updated.text[:180]}")
        if terminal:
            initiative_status = {"won": "succeeded", "lost": "failed", "inconclusive": "inconclusive"}[result["status"]]
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/os1_initiatives?id=eq.{experiment['initiative_id']}",
                headers=_headers("return=minimal"),
                json={
                    "status": initiative_status,
                    "actual_result": result,
                    "outcome_score": 1 if result["status"] == "won" else (0 if result["status"] == "lost" else None),
                    "attribution_confidence": result["attribution_confidence"],
                    "evaluated_at": result["evaluated_at"],
                    "completed_at": result["evaluated_at"],
                },
                timeout=TIMEOUT,
            )
            if experiment.get("hypothesis_id"):
                hypothesis_status = {"won": "supported", "lost": "rejected", "inconclusive": "inconclusive"}[result["status"]]
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/os1_hypotheses?id=eq.{experiment['hypothesis_id']}",
                    headers=_headers("return=minimal"),
                    json={"status": hypothesis_status},
                    timeout=TIMEOUT,
                )
            event = {
                "business_id": experiment["business_id"],
                "initiative_id": experiment["initiative_id"],
                "event_type": "experiment_evaluated",
                "from_status": "measuring",
                "to_status": initiative_status,
                "actor_type": "system",
                "reason": "Measurement window evaluated against explicit success criteria.",
                "evidence": result,
                "idempotency_key": f"experiment:{experiment['id']}:{result['status']}",
            }
            await client.post(
                f"{SUPABASE_URL}/rest/v1/os1_initiative_events",
                headers=_headers("return=minimal"),
                json=event,
                timeout=TIMEOUT,
            )
    return result


async def evaluate_experiments_for_observation(
    business_id: str,
    goal_id: str,
    metric_key: str,
) -> list[dict]:
    _ready()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SUPABASE_URL}/rest/v1/os1_experiments",
            headers=_headers(),
            params={
                "select": "*",
                "business_id": f"eq.{business_id}",
                "goal_id": f"eq.{goal_id}",
                "primary_metric_key": f"eq.{metric_key}",
                "status": "eq.running",
            },
            timeout=TIMEOUT,
        )
    if response.status_code != 200:
        raise MeasurementUnavailable(f"Could not load experiments: {response.text[:180]}")
    return [await evaluate_experiment(item) for item in response.json()]


async def sweep_due_experiments(limit: int = 100) -> dict:
    """Idempotent state sweep; safe for every API replica to run periodically."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"status": "unavailable", "evaluated": 0}
    now = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/os1_experiments",
                headers=_headers(),
                params={
                    "select": "*",
                    "status": "eq.running",
                    "ends_at": f"lte.{now.isoformat()}",
                    "order": "ends_at.asc",
                    "limit": str(min(max(limit, 1), 500)),
                },
                timeout=TIMEOUT,
            )
        if response.status_code != 200:
            return {"status": "unavailable", "evaluated": 0, "error": response.text[:180]}
        results = [await evaluate_experiment(item, now=now) for item in response.json()]
        return {"status": "ok", "evaluated": len(results), "results": results}
    except Exception as exc:
        return {"status": "error", "evaluated": 0, "error": str(exc)[:300]}
