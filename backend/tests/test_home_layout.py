"""Batch 67 — Home layout model + natural-language command parser (pure logic)."""
from backend.lib.business import home_layout as hl


def test_default_layout_is_complete_and_renderable():
    lay = hl.default_layout()
    assert set(lay["order"]) == set(hl.BLOCK_KEYS)
    assert set(lay["layouts"]) == {"lg", "md", "sm", "xs"}
    # No block overflows its breakpoint's column count.
    for bp, cols in hl.COLS.items():
        for item in lay["layouts"][bp]:
            assert item["x"] + item["w"] <= cols
    # xs stacks one-per-row.
    assert all(it["w"] == 1 for it in lay["layouts"]["xs"])


def test_default_layout_respects_score_order_override():
    order = list(reversed(hl.BLOCK_KEYS))
    lay = hl.default_layout(order)
    assert lay["order"][0] == order[0]
    # Override that omits a block still includes every block (nothing dropped).
    lay2 = hl.default_layout(["biggest_risk"])
    assert set(lay2["order"]) == set(hl.BLOCK_KEYS)
    assert lay2["order"][0] == "biggest_risk"


def test_resolve_block_synonyms():
    assert hl.resolve_block("CRM") == "pipeline_status"
    assert hl.resolve_block("pipeline") == "pipeline_status"
    assert hl.resolve_block("leads") == "best_lead"
    assert hl.resolve_block("revenue") == "revenue_metrics"
    assert hl.resolve_block("my calendar") == "calendar_intelligence"
    assert hl.resolve_block("nonsense widget") is None


def test_move_crm_to_top():
    lay, reply, changed = hl.apply_command(hl.default_layout(), "move CRM to the top")
    assert changed
    assert lay["order"][0] == "pipeline_status"
    assert "top" in reply.lower()


def test_make_leads_bigger():
    base = hl.default_layout()
    before = base["sizes"]["best_lead"]["w"]
    lay, _reply, changed = hl.apply_command(base, "make Leads bigger")
    assert changed
    assert lay["sizes"]["best_lead"]["w"] > before


def test_hide_and_show_revenue():
    lay, _r, changed = hl.apply_command(hl.default_layout(), "hide revenue")
    assert changed and "revenue_metrics" in lay["hidden"]
    assert all(it["i"] != "revenue_metrics" for it in lay["layouts"]["lg"])
    lay2, _r2, changed2 = hl.apply_command(lay, "show revenue")
    assert changed2 and "revenue_metrics" not in lay2["hidden"]


def test_build_ceo_dashboard_preset():
    lay, reply, changed = hl.apply_command(hl.default_layout(), "build me a CEO dashboard")
    assert changed
    assert lay["order"][:2] == ["daily_briefing", "revenue_metrics"]
    assert "ceo" in reply.lower()


def test_build_generic_dashboard_routes_to_preset():
    lay, _reply, changed = hl.apply_command(hl.default_layout(), "build a dashboard for my restaurant agency")
    assert changed
    # Operations-flavored preset leads with tasks/calendar.
    assert lay["order"][1] in ("tasks_priorities", "calendar_intelligence")


def test_reset_returns_default():
    custom, _r, _c = hl.apply_command(hl.default_layout(), "move CRM to the top")
    lay, _reply, changed = hl.apply_command(custom, "reset to default layout")
    assert changed
    assert lay["order"] == hl.DEFAULT_ORDER


def test_unparseable_command_is_safe():
    lay, reply, changed = hl.apply_command(hl.default_layout(), "what's the weather")
    assert not changed
    assert "couldn't" in reply.lower() or "try" in reply.lower()


def test_derive_from_layouts_roundtrip():
    lay = hl.default_layout()
    order, sizes = hl.derive_from_layouts(lay["layouts"])
    assert set(order) == set(hl.BLOCK_KEYS)
    assert sizes["daily_briefing"]["w"] == hl.DEFAULT_SIZES["daily_briefing"]["w"]


def test_is_home_layout_command_gate():
    assert hl.is_home_layout_command("move CRM to top")
    assert hl.is_home_layout_command("hide the calendar")
    assert not hl.is_home_layout_command("draft an email to my client")


def test_normalize_blank_layout_yields_default():
    assert hl.normalize_layout(None)["order"] == hl.DEFAULT_ORDER
    assert hl.normalize_layout({})["order"] == hl.DEFAULT_ORDER


# ── Batch 68: custom blocks participate in the grid ──────────────────────────

CUSTOM = [{"key": "custom:exp1", "w": 4, "h": 4}]


def test_default_layout_includes_custom_block():
    lay = hl.default_layout(None, custom=CUSTOM)
    assert "custom:exp1" in lay["order"]
    assert "custom:exp1" in lay["sizes"]
    lg_keys = {it["i"] for it in lay["layouts"]["lg"]}
    assert "custom:exp1" in lg_keys
    # still no overflow
    for bp, cols in hl.COLS.items():
        for it in lay["layouts"][bp]:
            assert it["x"] + it["w"] <= cols


def test_normalize_adds_new_custom_block_to_stale_layout():
    # A saved layout that predates the custom block must still give it a slot.
    base = hl.default_layout()  # no custom
    merged = hl.normalize_layout(base, custom=CUSTOM)
    assert "custom:exp1" in {it["i"] for it in merged["layouts"]["lg"]}


def test_layout_command_preserves_custom_block():
    base = hl.default_layout(None, custom=CUSTOM)
    lay, _r, changed = hl.apply_command(base, "move CRM to the top", custom=CUSTOM)
    assert changed
    assert lay["order"][0] == "pipeline_status"
    assert "custom:exp1" in lay["order"]
    assert "custom:exp1" in {it["i"] for it in lay["layouts"]["lg"]}


def test_create_block_request_does_not_match_preset():
    # The exact failure case: this must NOT be parsed as a layout command — it goes to
    # the brain's dashboard__control tool instead.
    assert hl.parse_command("create a new block in my dashboard called my expenses that I can add and remove items in") is None
    assert hl.is_home_layout_command("make me a chart of my revenue") is False
    assert hl.is_home_layout_command("change the accent color to emerald") is False


def test_build_ceo_dashboard_still_matches_preset():
    op = hl.parse_command("build me a CEO dashboard")
    assert op and op["op"] == "preset" and op["preset"] == "ceo"
