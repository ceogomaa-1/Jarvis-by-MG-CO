"""
Metadata (structure-level) tools: type mapping, reserved-name retry, guarded deletes,
object/field/view creation shapes. The metadata API is mocked — no network.
"""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import metadata


_OBJECTS = [
    {"id": "obj-person", "nameSingular": "person", "namePlural": "people",
     "labelSingular": "Person", "labelPlural": "People", "isCustom": False,
     "_fields": [
         {"id": "f-name", "name": "name", "label": "Name", "type": "FULL_NAME", "isCustom": False},
         {"id": "f-created", "name": "createdAt", "label": "Creation date", "type": "DATE_TIME", "isCustom": False},
         {"id": "f-budget", "name": "budget", "label": "Budget", "type": "CURRENCY", "isCustom": True},
     ]},
]


class FakeMeta:
    """Records query_meta calls; can be told to fail the first createOneField (reserved name)."""
    def __init__(self, *, fail_first_field=False):
        self.calls = []
        self._fail_first_field = fail_first_field
        self._field_calls = 0

    async def query_meta(self, query, variables=None, *, action=""):
        self.calls.append((action, variables))
        if action == "Create field":
            self._field_calls += 1
            if self._fail_first_field and self._field_calls == 1:
                return ConnectorResult(ok=False, error="Multiple validation errors occurred while creating fields")
            return ConnectorResult(ok=True, data={"createOneField": {"id": "new-field", "name": "x"}})
        if action == "Create object":
            return ConnectorResult(ok=True, data={"createOneObject": {"id": "new-obj", "labelPlural": "Properties"}})
        if action == "Create view":
            return ConnectorResult(ok=True, data={"createView": {"id": "new-view", "name": "n"}})
        return ConnectorResult(ok=True, data={})


@pytest.fixture(autouse=True)
def _mock_objects(monkeypatch):
    async def _fetch_objects(client):
        return ConnectorResult(ok=True, data=_OBJECTS)
    async def _enum(client):
        return {"TEXT", "NUMBER", "CURRENCY", "DATE_TIME", "BOOLEAN", "SELECT", "MULTI_SELECT", "PHONES", "EMAILS", "LINKS"}
    monkeypatch.setattr(metadata, "fetch_objects", _fetch_objects)
    monkeypatch.setattr(metadata, "fetch_field_type_enum", _enum)


@pytest.mark.asyncio
async def test_create_field_maps_type_and_targets_object():
    c = FakeMeta()
    res = await metadata.create_field(c, "u", {"object": "People", "name": "Budget", "field_type": "currency"})
    assert res.ok
    _, v = [call for call in c.calls if call[0] == "Create field"][0]
    f = v["input"]["field"]
    assert f["type"] == "CURRENCY" and f["objectMetadataId"] == "obj-person" and f["name"] == "budget"


@pytest.mark.asyncio
async def test_create_select_field_builds_options():
    c = FakeMeta()
    res = await metadata.create_field(c, "u", {"object": "People", "name": "Tier", "field_type": "select",
                                               "options": ["Gold", "Silver"]})
    assert res.ok
    _, v = [call for call in c.calls if call[0] == "Create field"][0]
    opts = v["input"]["field"]["options"]
    assert [o["label"] for o in opts] == ["Gold", "Silver"]
    assert opts[0]["value"] == "GOLD"


@pytest.mark.asyncio
async def test_create_field_retries_reserved_name():
    c = FakeMeta(fail_first_field=True)
    res = await metadata.create_field(c, "u", {"object": "People", "name": "Address", "field_type": "text"})
    assert res.ok
    field_calls = [call for call in c.calls if call[0] == "Create field"]
    assert field_calls[0][1]["input"]["field"]["name"] == "address"        # first try
    assert field_calls[1][1]["input"]["field"]["name"] == "addressField"   # retry with suffix


@pytest.mark.asyncio
async def test_unsupported_type_errors():
    c = FakeMeta()
    res = await metadata.create_field(c, "u", {"object": "People", "name": "X", "field_type": "rocket"})
    assert not res.ok and "unsupported" in res.error.lower()


@pytest.mark.asyncio
async def test_delete_standard_field_refused():
    c = FakeMeta()
    res = await metadata.delete_field(c, "u", {"object": "People", "field": "Name"})
    assert not res.ok and "standard" in res.error.lower()
    assert not any(call[0] == "Delete field" for call in c.calls)


@pytest.mark.asyncio
async def test_delete_custom_field_ok():
    c = FakeMeta()
    res = await metadata.delete_field(c, "u", {"object": "People", "field": "Budget"})
    assert res.ok and res.data["status"] == "deleted"


@pytest.mark.asyncio
async def test_create_object_derives_names_and_fields():
    c = FakeMeta()
    res = await metadata.create_object(c, "u", {"name": "Properties", "fields": [
        {"name": "Address", "type": "text"}, {"name": "Price", "type": "currency"}]})
    assert res.ok
    _, v = [call for call in c.calls if call[0] == "Create object"][0]
    obj = v["input"]["object"]
    assert obj["nameSingular"] == "property" and obj["namePlural"] == "properties"
    assert len([call for call in c.calls if call[0] == "Create field"]) == 2


@pytest.mark.asyncio
async def test_create_view_sets_icon_and_sort():
    c = FakeMeta()
    res = await metadata.create_view(c, "u", {"object": "People", "name": "Recent",
                                              "sort_by": "creation date", "sort_direction": "desc"})
    assert res.ok
    _, v = [call for call in c.calls if call[0] == "Create view"][0]
    assert v["input"]["icon"] and v["input"]["type"] == "TABLE"
    sort = [call for call in c.calls if call[0] == "Create view sort"][0][1]
    assert sort["input"]["fieldMetadataId"] == "f-created" and sort["input"]["direction"] == "DESC"
