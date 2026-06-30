"""Batch 68 — Dashboard Studio pure helpers (data normalization + view/layout shaping)."""
from backend.lib.business import dashboard_studio as ds


def test_norm_items_handles_strings_and_dicts():
    items = ds._norm_items(["Rent", {"label": "Coffee", "amount": "4.50"}, {"name": "Gas", "cost": 30}], want_amount=True)
    assert items[0]["label"] == "Rent" and "amount" not in items[0]
    assert items[1]["label"] == "Coffee" and items[1]["amount"] == 4.5
    assert items[2]["label"] == "Gas" and items[2]["amount"] == 30.0
    assert all("id" in i for i in items)


def test_norm_items_chart_uses_value_key():
    pts = ds._norm_items([{"label": "Jan", "value": 30}, {"label": "Feb", "value": 45}], want_amount=False)
    assert pts[0]["value"] == 30.0 and "amount" not in pts[0]


def test_list_total():
    items = ds._norm_items([{"label": "a", "amount": 10}, {"label": "b", "amount": 5.25}], want_amount=True)
    assert ds._list_total(items) == 15.25


def test_block_to_view_shape():
    row = {"id": "abc123", "block_type": "list", "title": "My Expenses",
           "config": {"unit": "$"}, "data": {"items": [], "total": 0}, "style": {}}
    v = ds.block_to_view(row)
    assert v["block_key"] == "custom:abc123"
    assert v["custom"] is True and v["custom_type"] == "list"
    assert v["title"] == "My Expenses"


def test_custom_layout_specs_sizes_by_type():
    views = [
        {"block_key": "custom:1", "custom_type": "list"},
        {"block_key": "custom:2", "custom_type": "metric"},
        {"block_key": "custom:3", "custom_type": "chart"},
    ]
    specs = ds.custom_layout_specs(views)
    by_key = {s["key"]: s for s in specs}
    assert by_key["custom:1"]["h"] == ds.TYPE_SIZE["list"]["h"]
    assert by_key["custom:2"]["w"] == ds.TYPE_SIZE["metric"]["w"]
    assert by_key["custom:3"]["w"] == ds.TYPE_SIZE["chart"]["w"]
