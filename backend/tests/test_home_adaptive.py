"""Batch 67 — Phase 3 adaptive Home: engagement ranking + proposal logic (pure)."""
from backend.lib.business.operator import home_adaptive as ha


def test_rank_engagement_weights_first_actions_highest():
    events = [
        {"block_key": "pipeline_status", "event_type": "first_action"},
        {"block_key": "pipeline_status", "event_type": "click_through"},
        {"block_key": "best_lead", "event_type": "click_through"},
        {"block_key": "calendar_intelligence", "event_type": "view"},
        {"block_key": "revenue_metrics", "event_type": "view"},
    ]
    ranked = ha.rank_engagement(events)
    assert ranked[0] == "pipeline_status"   # first_action(3) + click_through(2) = 5
    assert ranked[1] == "best_lead"          # click_through(2)


def test_rank_engagement_ignores_unknown_blocks():
    ranked = ha.rank_engagement([{"block_key": "bogus", "event_type": "first_action"}])
    assert ranked == []


def test_propose_order_keeps_all_blocks():
    order = ha.propose_order(["calendar_intelligence", "pipeline_status"])
    assert order[:2] == ["calendar_intelligence", "pipeline_status"]
    assert set(order) == set(ha.hl.BLOCK_KEYS)


def test_meaningfully_different_detects_reorder():
    cur = list(ha.hl.BLOCK_KEYS)
    same = list(ha.hl.BLOCK_KEYS)
    moved = ["pipeline_status"] + [k for k in ha.hl.BLOCK_KEYS if k != "pipeline_status"]
    assert ha._meaningfully_different(moved, cur) is True
    assert ha._meaningfully_different(same, cur) is False


def test_build_suggestion_message_names_top_flow():
    msg = ha.build_suggestion_message(["pipeline_status", "best_lead", "calendar_intelligence"])
    assert "Pipeline Status" in msg and "→" in msg
