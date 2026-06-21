"""
Twenty migration — pure mapping/naming logic (no live Twenty needed).

These pin the decisions that shape the mirrored schema: GHL field types -> Twenty
types, option extraction, and the deterministic identifier generation that makes
re-running the mirror idempotent.
"""
from backend.lib.business.twenty import field_map
from backend.lib.business.twenty.naming import to_camel, to_option_value


def test_ghl_type_mapping_core():
    assert field_map.ghl_type_to_twenty("TEXT") == "TEXT"
    assert field_map.ghl_type_to_twenty("NUMERICAL") == "NUMBER"
    assert field_map.ghl_type_to_twenty("MONETORY") == "CURRENCY"   # GHL's spelling
    assert field_map.ghl_type_to_twenty("SINGLE_OPTIONS") == "SELECT"
    assert field_map.ghl_type_to_twenty("MULTIPLE_OPTIONS") == "MULTI_SELECT"
    assert field_map.ghl_type_to_twenty("DATE") == "DATE_TIME"


def test_unknown_and_empty_type_default_to_text():
    assert field_map.ghl_type_to_twenty("SOMETHING_NEW") == "TEXT"
    assert field_map.ghl_type_to_twenty(None) == "TEXT"
    assert field_map.ghl_type_to_twenty("") == "TEXT"


def test_needs_options_only_for_select_types():
    assert field_map.needs_options("SELECT") is True
    assert field_map.needs_options("MULTI_SELECT") is True
    assert field_map.needs_options("TEXT") is False
    assert field_map.needs_options("CURRENCY") is False


def test_extract_options_handles_strings_and_dicts_and_dedupes():
    assert field_map.extract_ghl_options({"options": ["Hot", "Warm", "Cold"]}) == ["Hot", "Warm", "Cold"]
    field = {"options": [{"label": "Hot"}, {"value": "Warm"}, {"name": "Hot"}]}
    assert field_map.extract_ghl_options(field) == ["Hot", "Warm"]
    assert field_map.extract_ghl_options({}) == []


def test_to_camel_is_deterministic_and_valid():
    assert to_camel("Lead Source") == "leadSource"
    assert to_camel("Budget (CAD)") == "budgetCad"
    # leading digit can't start an identifier
    assert to_camel("1st Touch")[0].isalpha()
    # stable across calls -> idempotent field names
    assert to_camel("Lead Source") == to_camel("Lead Source")


def test_to_option_value_upper_snake():
    assert to_option_value("In Progress") == "IN_PROGRESS"
    assert to_option_value("Closed - Won") == "CLOSED_WON"
    assert to_option_value("")[0].isalpha()
