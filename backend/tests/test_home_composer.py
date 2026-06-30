"""Batch 67 — Home composer: explainable scoring + block composition (pure logic)."""
from backend.lib.business.operator import home_composer as hc


def test_score_block_weights_and_clamping():
    total, breakdown = hc.score_block(100, 100, 100, 100)
    assert total == 100.0
    assert breakdown["weights"] == hc.WEIGHTS
    # Out-of-range inputs clamp to [0, 100]; weighted sum stays bounded.
    total2, bd2 = hc.score_block(-50, 200, 0, 0)
    assert 0 <= total2 <= 100
    assert bd2["urgency"] == 0.0 and bd2["value"] == 100.0


def test_score_breakdown_persists_components():
    _, bd = hc.score_block(80, 60, 40, 20)
    assert set(bd) == {"urgency", "value", "risk", "recency", "weights"}
    assert bd["urgency"] == 80.0 and bd["risk"] == 40.0


def _empty_signals():
    return {"user": [{"company_name": "Acme"}], "metrics": [], "flags": [],
            "run": [], "pending": [], "leads": []}


def test_build_blocks_returns_all_ten_sorted_and_actionable():
    blocks = hc.build_blocks(_empty_signals(), "", "Acme")
    keys = {b["block_key"] for b in blocks}
    assert keys == set(hc.BLOCK_KEYS)
    # Every block carries a primary action — Home never hands the user homework.
    for b in blocks:
        assert b["primary_action"] and b["primary_action"].get("kind") in {"chat", "navigate", "connect"}
        assert "ai_summary" in b and b["ai_summary"]
        assert "score_breakdown" in b
    # Default order is the explainable score, descending.
    scores = [b["score"] for b in blocks]
    assert scores == sorted(scores, reverse=True)


def test_empty_signals_mark_connection_blocks_not_crash():
    blocks = {b["block_key"]: b for b in hc.build_blocks(_empty_signals(), "", "Acme")}
    # With no leads/metrics/calendar these honestly ask the user to connect a source.
    assert blocks["best_lead"]["status"] == "needs_connection"
    assert blocks["revenue_metrics"]["status"] == "needs_connection"
    assert blocks["calendar_intelligence"]["status"] == "needs_connection"


def test_rich_signals_surface_risk_lead_and_followup():
    signals = {
        "user": [{"company_name": "Acme", "industry": "agency"}],
        "metrics": [{"metrics_text": "Revenue up +12% MoM, mostly referrals.", "updated_at": "2026-06-30T08:00:00Z"}],
        "flags": [{"flag_summary": "Top client hasn't replied in 14 days — going cold.",
                   "flag_severity": "high", "created_at": "2026-06-30T06:00:00Z"}],
        "run": [{"id": "r1", "completed_at": "2026-06-30T02:30:00Z",
                 "packager_output": {"morning_message": "Three moves queued for you."},
                 "strategist_output": {"moves": [{"title": "Launch referral program", "rationale": "Referrals drive growth."}]}}],
        "pending": [{"title": "Follow up with Globex", "description": "They went cold; call them.",
                     "internal_or_external": "external", "priority": 10, "created_at": "2026-06-30T05:00:00Z"}],
        "leads": [{"name": "Initech", "score": 88, "tier": "A", "phone": "555-1000",
                   "website": "initech.com", "category": "SaaS", "pushed": False, "created_at": "2026-06-30T01:00:00Z"}],
    }
    blocks = {b["block_key"]: b for b in hc.build_blocks(signals, "", "Acme")}

    assert "+12%" in blocks["revenue_metrics"]["ai_summary"]
    assert blocks["biggest_risk"]["status"] == "ok"
    assert "cold" in blocks["biggest_risk"]["ai_summary"].lower()
    assert "Initech" in blocks["best_lead"]["ai_summary"]
    assert blocks["best_lead"]["primary_action"]["kind"] == "chat"
    assert "Globex" in blocks["urgent_follow_up"]["ai_summary"]
    assert "referral" in blocks["ai_recommendations"]["ai_summary"].lower()
    # High-severity risk should outscore an empty-state block.
    assert blocks["biggest_risk"]["score"] > 50


def test_chat_and_nav_action_helpers():
    a = hc.chat_action("Call them", "Call the client")
    assert a == {"label": "Call them", "kind": "chat", "prompt": "Call the client"}
    n = hc.nav_action("Open CRM", "crm")
    assert n == {"label": "Open CRM", "kind": "navigate", "target": "crm"}
