"""Batch 76 — Goal Engine domain tests (no network)."""
from datetime import datetime, timezone

import pytest

from backend.lib.business.goal_engine import _criterion_met, calculate_goal_health, format_goal_snapshot
from backend.lib.business.measurement_engine import evaluate_measurement
from backend.lib.business.identity import user_id_to_uuid, uuid_to_app_user_id


USER_UUID = "3363afdc-9bca-4b88-893c-f535c62a6687"
APP_USER_ID = "user_3363afdc9bca4b88893cf535c62a6687"


def test_identity_boundary_accepts_both_supported_shapes():
    assert user_id_to_uuid(USER_UUID) == USER_UUID
    assert user_id_to_uuid(APP_USER_ID) == USER_UUID
    assert uuid_to_app_user_id(USER_UUID) == APP_USER_ID
    with pytest.raises(ValueError):
        user_id_to_uuid("user_not-a-real-user")


def test_goal_health_compares_progress_to_elapsed_time():
    goal = {
        "baseline_value": 0,
        "current_value": 500,
        "target_value": 1000,
        "direction": "increase",
        "start_at": "2026-01-01T00:00:00Z",
        "deadline": "2026-01-11T00:00:00Z",
    }
    health = calculate_goal_health(goal, now=datetime(2026, 1, 6, tzinfo=timezone.utc))
    assert health["progress_percent"] == 50.0
    assert health["elapsed_ratio"] == 0.5
    assert health["health"] == "on_track"
    assert health["required_daily_change"] == 100.0


def test_goal_health_flags_a_goal_that_is_materially_behind_pace():
    goal = {
        "baseline_value": 0,
        "current_value": 100,
        "target_value": 1000,
        "direction": "increase",
        "start_at": "2026-01-01T00:00:00Z",
        "deadline": "2026-01-11T00:00:00Z",
    }
    health = calculate_goal_health(goal, now=datetime(2026, 1, 8, tzinfo=timezone.utc))
    assert health["progress_percent"] == 10.0
    assert health["health"] == "off_track"


def test_goal_health_supports_decrease_targets():
    goal = {
        "baseline_value": 10,
        "current_value": 2,
        "target_value": 2,
        "direction": "decrease",
        "start_at": "2026-01-01T00:00:00Z",
        "deadline": "2026-02-01T00:00:00Z",
    }
    health = calculate_goal_health(goal, now=datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert health["achieved"] is True
    assert health["health"] == "achieved"
    assert health["progress_percent"] == 100.0


def test_operator_goal_context_contains_state_not_just_a_label():
    snapshot = {
        "goal": {
            "objective": "Reach $30k MRR",
            "metric_key": "monthly_recurring_revenue",
            "unit": "cad",
            "baseline_value": 6000,
            "current_value": 9000,
            "target_value": 30000,
            "deadline": "2027-03-01T00:00:00Z",
            "health": {
                "progress_percent": 12.5,
                "health": "at_risk",
                "required_daily_change": 88.0,
                "remaining_days": 239,
            },
            "constraints": ["Maximum $4k acquisition spend"],
            "leading_indicators": ["qualified_calls"],
        },
        "bottlenecks": [{"title": "Too few qualified conversations", "evidence": "Only 3 calls last month"}],
        "initiative_counts": {"needs_approval": 2, "measuring": 1},
    }
    context = format_goal_snapshot(snapshot)
    assert "Reach $30k MRR" in context
    assert "baseline 6000" in context
    assert "current 9000" in context
    assert "at_risk" in context
    assert "Too few qualified conversations" in context
    assert "needs_approval=2" in context


def test_success_criteria_comparators_are_deterministic():
    assert _criterion_met(">=", 4, 4) is True
    assert _criterion_met(">=", 3, 4) is False
    assert _criterion_met("<=", 2, 3) is True
    assert _criterion_met("=", 7, 7) is True
    assert _criterion_met("bogus", 7, 7) is False


def test_measurement_wins_only_when_target_is_observed():
    experiment = {
        "starts_at": "2026-01-01T00:00:00Z",
        "ends_at": "2026-01-08T00:00:00Z",
        "baseline_value": 10,
        "target_operator": ">=",
        "target_value": 20,
    }
    result = evaluate_measurement(
        experiment,
        [
            {"value": 14, "observed_at": "2026-01-03T00:00:00Z"},
            {"value": 22, "observed_at": "2026-01-05T00:00:00Z"},
        ],
        now=datetime(2026, 1, 6, tzinfo=timezone.utc),
    )
    assert result["status"] == "won"
    assert result["absolute_delta"] == 12
    assert result["sample_count"] == 2
    assert result["attribution_confidence"] < 1


def test_measurement_waits_until_window_closes_before_calling_a_loss():
    experiment = {
        "starts_at": "2026-01-01T00:00:00Z",
        "ends_at": "2026-01-08T00:00:00Z",
        "baseline_value": 10,
        "target_operator": ">=",
        "target_value": 20,
    }
    observations = [{"value": 15, "observed_at": "2026-01-05T00:00:00Z"}]
    running = evaluate_measurement(
        experiment, observations, now=datetime(2026, 1, 6, tzinfo=timezone.utc)
    )
    lost = evaluate_measurement(
        experiment, observations, now=datetime(2026, 1, 9, tzinfo=timezone.utc)
    )
    assert running["status"] == "running"
    assert lost["status"] == "lost"


def test_closed_measurement_without_evidence_is_inconclusive():
    result = evaluate_measurement(
        {
            "starts_at": "2026-01-01T00:00:00Z",
            "ends_at": "2026-01-02T00:00:00Z",
            "baseline_value": 10,
            "target_operator": "<=",
            "target_value": 5,
        },
        [],
        now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    assert result["status"] == "inconclusive"
    assert result["attribution_confidence"] == 0


def test_post_window_observation_cannot_rewrite_a_failed_experiment():
    result = evaluate_measurement(
        {
            "starts_at": "2026-01-01T00:00:00Z",
            "ends_at": "2026-01-08T00:00:00Z",
            "baseline_value": 10,
            "target_operator": ">=",
            "target_value": 20,
        },
        [
            {"value": 15, "observed_at": "2026-01-07T00:00:00Z"},
            {"value": 25, "observed_at": "2026-01-09T00:00:00Z"},
        ],
        now=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )
    assert result["status"] == "lost"
    assert result["latest_value"] == 15
