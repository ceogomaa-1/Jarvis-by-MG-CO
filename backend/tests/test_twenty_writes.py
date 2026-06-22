"""
Phase 3 — Jarvis CRM write tools: correctness, idempotency, guardrails, isolation.

Mocks the Twenty client + the Supabase-backed maps so no network is touched.
Proves: writes build mutations from the introspected schema (no guessed fields),
create_person is idempotent on email, stage moves resolve via the structure map,
deletes are confirm-gated, and every write is scoped to the per-user workspace.
"""
import json

import pytest

from backend.lib.business.twenty import tools as tools_mod
from backend.lib.business.twenty import writes
from backend.lib.business.twenty.introspect import TwentyField, TwentyObject, TwentySchema


def _schema() -> TwentySchema:
    person = TwentyObject(
        id="obj-person", name_singular="person", name_plural="people", label_singular="Person",
        fields=[
            TwentyField(id="f1", name="name", label="Name", type="FULL_NAME", is_custom=False),
            TwentyField(id="f2", name="emails", label="Emails", type="EMAILS", is_custom=False),
            TwentyField(id="f3", name="ghlTags", label="Tags", type="MULTI_SELECT", is_custom=True),
        ],
    )
    opp = TwentyObject(
        id="obj-opp", name_singular="opportunity", name_plural="opportunities", label_singular="Opportunity",
        fields=[
            TwentyField(id="o1", name="name", label="Name", type="TEXT", is_custom=False),
            TwentyField(id="o2", name="stage", label="Stage", type="SELECT", is_custom=False),
            TwentyField(id="o3", name="amount", label="Amount", type="CURRENCY", is_custom=False),
        ],
    )
    note = TwentyObject(id="obj-note", name_singular="note", name_plural="notes", label_singular="Note",
                        fields=[TwentyField(id="n1", name="body", label="Body", type="TEXT", is_custom=False)])
    note_t = TwentyObject(id="obj-nt", name_singular="noteTarget", name_plural="noteTargets", label_singular="NoteTarget", fields=[])
    return TwentySchema(objects={"person": person, "opportunity": opp, "note": note, "noteTarget": note_t}, field_types=set())


class FakeClient:
    """Records mutations; answers people/opportunity reads from seeded data."""
    def __init__(self, *, api_key="key", people=None, opps=None):
        self.api_key = api_key
        self.mutations = []
        self._people = people or []
        self._opps = opps or []

    async def query_data(self, query, variables=None, *, action=""):
        from backend.lib.business.connectors.base import ConnectorResult
        q = query
        if query.strip().startswith("mutation"):
            self.mutations.append((action, variables))
            # echo a new id for creates
            return ConnectorResult(ok=True, data={
                "createPerson": {"id": "new-person"}, "createOpportunity": {"id": "new-opp"},
                "createNote": {"id": "new-note"}, "createNoteTarget": {"id": "nt"},
                "updatePerson": {"id": (variables or {}).get("id")},
                "updateOpportunity": {"id": (variables or {}).get("id")},
                "deletePerson": {"id": (variables or {}).get("id")},
                "deleteOpportunity": {"id": (variables or {}).get("id")},
            })
        if "people" in q:
            return ConnectorResult(ok=True, data={"people": {"edges": [{"node": n} for n in self._people]}})
        if "opportunities" in q:
            return ConnectorResult(ok=True, data={"opportunities": {"edges": [{"node": o} for o in self._opps]}})
        return ConnectorResult(ok=True, data={})


@pytest.fixture(autouse=True)
def _no_structure(monkeypatch):
    async def _empty(_uid):
        return {}
    monkeypatch.setattr(writes.store, "load_structure_map", _empty)


@pytest.mark.asyncio
async def test_create_person_builds_composite_input():
    c = FakeClient()
    res = await writes.create_person(c, _schema(), "user_x", {"first_name": "Test", "last_name": "Lead", "email": "t@l.co"})
    assert res.ok and res.data["created"] is True
    _, vars = c.mutations[0]
    assert vars["data"]["name"] == {"firstName": "Test", "lastName": "Lead"}
    assert vars["data"]["emails"]["primaryEmail"] == "t@l.co"


@pytest.mark.asyncio
async def test_create_person_idempotent_on_email():
    existing = {"id": "p1", "name": {"firstName": "Test", "lastName": "Lead"}, "emails": {"primaryEmail": "t@l.co"}}
    c = FakeClient(people=[existing])
    res = await writes.create_person(c, _schema(), "user_x", {"first_name": "Test", "email": "t@l.co"})
    assert res.ok and res.data["created"] is False
    assert res.data["id"] == "p1"
    assert c.mutations == []  # no create mutation fired


@pytest.mark.asyncio
async def test_move_stage_resolves_via_structure_map(monkeypatch):
    async def _struct(_uid):
        return {("stage", "ghl-1"): {"twenty_id": "WON", "extra": {"label": "Won", "field_name": "stage"}}}
    monkeypatch.setattr(writes.store, "load_structure_map", _struct)
    c = FakeClient(opps=[{"id": "o1", "name": "Big Deal"}])
    res = await writes.move_opportunity_stage(c, _schema(), "user_x", {"query": "Big Deal", "stage": "Won"})
    assert res.ok
    _, vars = c.mutations[0]
    assert vars["id"] == "o1" and vars["data"] == {"stage": "WON"}


@pytest.mark.asyncio
async def test_move_stage_resolves_via_native_options_without_import():
    """No GHL structure map — stage resolves from Twenty's native SELECT options."""
    schema = _schema()
    schema.obj("opportunity").field_by_name("stage").options = [
        {"value": "NEW", "label": "New"}, {"value": "PROPOSAL", "label": "Proposal"},
    ]
    c = FakeClient(opps=[{"id": "o1", "name": "Deal"}])
    res = await writes.move_opportunity_stage(c, schema, "user_x", {"query": "Deal", "stage": "Proposal"})
    assert res.ok
    _, vars = c.mutations[0]
    assert vars["data"] == {"stage": "PROPOSAL"}   # matched by label → option value


@pytest.mark.asyncio
async def test_move_stage_unknown_lists_known(monkeypatch):
    async def _struct(_uid):
        return {("stage", "g"): {"twenty_id": "NEW", "extra": {"label": "New", "field_name": "stage"}}}
    monkeypatch.setattr(writes.store, "load_structure_map", _struct)
    c = FakeClient(opps=[{"id": "o1", "name": "Deal"}])
    res = await writes.move_opportunity_stage(c, _schema(), "user_x", {"query": "Deal", "stage": "Nonsense"})
    assert not res.ok and "new" in res.error.lower()


@pytest.mark.asyncio
async def test_add_tag_is_idempotent():
    person = {"id": "p1", "name": {"firstName": "A", "lastName": "B"}, "emails": {"primaryEmail": "a@b.co"}, "ghlTags": ["VIP"]}
    c = FakeClient(people=[person])
    res = await writes.add_tag(c, _schema(), "user_x", {"query": "a@b.co", "tag": "VIP"})
    assert res.ok and res.data.get("idempotent") is True
    assert c.mutations == []  # already tagged → no update


@pytest.mark.asyncio
async def test_delete_person_summary():
    c = FakeClient(people=[{"id": "p9", "name": {"firstName": "Gone", "lastName": ""}, "emails": {}}])
    res = await writes.delete_person(c, _schema(), "user_x", {"query": "Gone"})
    assert res.ok and res.data["status"] == "deleted"
    assert c.mutations[0][0] == "Delete person"


def test_deletes_are_confirm_gated():
    from backend.routes.business.chat import WRITE_ACTIONS, CRM_WRITE_ACTIONS
    assert "twenty__delete_person" in WRITE_ACTIONS
    assert "twenty__delete_opportunity" in WRITE_ACTIONS
    # non-destructive writes are NOT in the hold-to-confirm set
    assert "twenty__create_person" not in WRITE_ACTIONS
    # but every write does signal a CRM refresh
    assert "twenty__create_person" in CRM_WRITE_ACTIONS


@pytest.mark.asyncio
async def test_writes_scoped_to_per_user_workspace(monkeypatch):
    """execute_twenty_tool resolves the user's OWN client before writing — isolation."""
    seen = {}

    async def _for_user(uid):
        return FakeClient(api_key=f"key-{uid}")

    async def _introspect(_client):
        from backend.lib.business.connectors.base import ConnectorResult
        return ConnectorResult(ok=True, data=_schema())

    async def _fake_create(client, schema, user_id, inp):
        from backend.lib.business.connectors.base import ConnectorResult
        seen["api_key"] = client.api_key
        return ConnectorResult(ok=True, data={"summary": "ok"})

    monkeypatch.setattr(tools_mod.TwentyClient, "for_user", classmethod(lambda cls, uid: _for_user(uid)))
    monkeypatch.setattr(tools_mod, "introspect", _introspect)
    monkeypatch.setitem(writes.WRITE_HANDLERS, "create_person", _fake_create)

    await tools_mod.execute_twenty_tool("create_person", {"first_name": "X"}, "user_AAA")
    assert seen["api_key"] == "key-user_AAA"
    await tools_mod.execute_twenty_tool("create_person", {"first_name": "Y"}, "user_BBB")
    assert seen["api_key"] == "key-user_BBB"
