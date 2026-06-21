"""
Twenty importer — idempotency (the property that lets us re-run safely).

Mocks the Twenty client + the Supabase-backed maps so no network is touched, then
runs the importer twice over the same fake GHL data: the first pass creates records,
the second pass creates ZERO (everything is found in crm_import_map).
"""
import pytest

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty import importer as importer_mod
from backend.lib.business.twenty import store
from backend.lib.business.twenty.importer import Importer
from backend.lib.business.twenty.introspect import TwentyField, TwentyObject, TwentySchema


def _schema() -> TwentySchema:
    person = TwentyObject(
        id="obj-person", name_singular="person", name_plural="people", label_singular="Person",
        fields=[
            TwentyField(id="f1", name="name", label="Name", type="FULL_NAME", is_custom=False),
            TwentyField(id="f2", name="emails", label="Emails", type="EMAILS", is_custom=False),
        ],
    )
    company = TwentyObject(id="obj-co", name_singular="company", name_plural="companies", label_singular="Company",
                           fields=[TwentyField(id="c1", name="name", label="Name", type="TEXT", is_custom=False)])
    opp = TwentyObject(id="obj-opp", name_singular="opportunity", name_plural="opportunities", label_singular="Opportunity",
                       fields=[TwentyField(id="o1", name="name", label="Name", type="TEXT", is_custom=False)])
    note = TwentyObject(id="obj-note", name_singular="note", name_plural="notes", label_singular="Note", fields=[])
    task = TwentyObject(id="obj-task", name_singular="task", name_plural="tasks", label_singular="Task", fields=[])
    return TwentySchema(objects={"person": person, "company": company, "opportunity": opp, "note": note, "task": task},
                        field_types=set())


class _FakeClient:
    def __init__(self):
        self.create_calls = 0

    async def query_data(self, query, variables=None, *, action=""):
        self.create_calls += 1
        # The selection field (e.g. "createPerson") is the token after the first "{".
        field = query.split("{", 1)[1].strip().split("(")[0].strip()
        return ConnectorResult(ok=True, data={field: {"id": f"tw-{self.create_calls}"}})

    async def query_meta(self, *a, **k):
        return ConnectorResult(ok=True, data={})


class _FakeGHL:
    def __init__(self, contacts):
        self._contacts = contacts

    async def list_contacts_v2(self, limit=100, start_after_id=None, start_after=None):
        if start_after_id or start_after:
            return ConnectorResult(ok=True, data={"contacts": [], "meta": {}})
        return ConnectorResult(ok=True, data={"contacts": self._contacts, "meta": {}})

    async def get_contact_notes(self, contact_id):
        return ConnectorResult(ok=True, data={"notes": []})

    async def get_contact_tasks(self, contact_id):
        return ConnectorResult(ok=True, data={"tasks": []})

    async def list_businesses(self):
        return ConnectorResult(ok=True, data={"businesses": []})


@pytest.fixture
def memory_maps(monkeypatch):
    """In-memory stand-in for the Supabase-backed crm_import_map."""
    imap: dict = {}

    async def fake_load_structure_map(user_id):
        return {}

    async def fake_load_import_map(user_id):
        return dict(imap)

    async def fake_record_import(user_id, ghl_id, twenty_id, record_type):
        imap[(record_type, ghl_id)] = twenty_id
        return True

    monkeypatch.setattr(store, "load_structure_map", fake_load_structure_map)
    monkeypatch.setattr(store, "load_import_map", fake_load_import_map)
    monkeypatch.setattr(store, "record_import", fake_record_import)
    # importer.py imported the module object, so patching the module attrs is enough
    return imap


@pytest.mark.asyncio
async def test_import_is_idempotent(memory_maps):
    contacts = [
        {"id": "c1", "firstName": "Ada", "lastName": "Lovelace", "email": "ada@x.com"},
        {"id": "c2", "firstName": "Alan", "lastName": "Turing", "email": "alan@x.com"},
    ]
    schema = _schema()
    structure = {"pipelines": [], "custom_fields": [], "tags": []}

    # First run — creates both people.
    client1 = _FakeClient()
    imp1 = Importer(client1, schema, "user-1")
    summary1 = await imp1.run(_FakeGHL(contacts), structure)
    assert summary1["person"]["created"] == 2
    assert summary1["person"]["skipped"] == 0
    assert client1.create_calls == 2

    # Second run — everything already mapped, zero new creates.
    client2 = _FakeClient()
    imp2 = Importer(client2, schema, "user-1")
    summary2 = await imp2.run(_FakeGHL(contacts), structure)
    assert summary2["person"]["created"] == 0
    assert summary2["person"]["skipped"] == 2
    assert client2.create_calls == 0


@pytest.mark.asyncio
async def test_person_input_only_sets_known_fields(memory_maps):
    """Defensive builder: a field absent from the schema is never sent."""
    schema = _schema()
    imp = Importer(_FakeClient(), schema, "user-1")
    imp.struct = importer_mod.StructMaps({})
    data = imp._person_input({"firstName": "Ada", "email": "ada@x.com", "phone": "555"}, None)
    assert data["name"] == {"firstName": "Ada", "lastName": ""}
    assert data["emails"]["primaryEmail"] == "ada@x.com"
    # 'phones' is NOT in the schema fixture -> must be omitted, not guessed
    assert "phones" not in data
