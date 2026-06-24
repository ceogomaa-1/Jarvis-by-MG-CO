"""
Custom-field writes: the generalized create/update/bulk path that resolves ANY field by
name/label + type from the live schema, maps SELECT labels→option keys, formats link
fields, and supports reliable bulk updates + the domain→link re-home one-shot fix.

Mirrors the real workspace Mohamed hit: Companies with Status (select), Job Status
(select), Google Maps Link (link). Network is mocked.
"""
import pytest

from backend.lib.business.twenty import writes
from backend.lib.business.twenty.introspect import TwentyField, TwentyObject, TwentySchema


def _schema() -> TwentySchema:
    company = TwentyObject(
        id="obj-co", name_singular="company", name_plural="companies", label_singular="Company",
        fields=[
            TwentyField(id="c1", name="name", label="Name", type="TEXT", is_custom=False),
            TwentyField(id="c2", name="domainName", label="Domain", type="LINKS", is_custom=False),
            TwentyField(id="c3", name="status", label="Status", type="SELECT", is_custom=True, options=[
                {"value": "TO_BE_CALLED", "label": "To Be Called"}, {"value": "CALLED", "label": "Called"},
                {"value": "ANSWERED", "label": "Answered"}, {"value": "NO_ANSWER", "label": "No Answer"},
                {"value": "FOLLOW_UP", "label": "Follow Up"}]),
            TwentyField(id="c4", name="jobStatus", label="Job Status", type="SELECT", is_custom=True, options=[
                {"value": "PENDING", "label": "Pending"}, {"value": "DONE", "label": "Done"},
                {"value": "CANCELLED", "label": "Cancelled"}]),
            TwentyField(id="c5", name="googleMapsLink", label="Google Maps Link", type="LINKS", is_custom=True),
        ],
    )
    person = TwentyObject(id="obj-p", name_singular="person", name_plural="people", label_singular="Person", fields=[
        TwentyField(id="p1", name="name", label="Name", type="FULL_NAME", is_custom=False)])
    return TwentySchema(objects={"company": company, "person": person}, field_types=set())


class FakeClient:
    def __init__(self, cos=None):
        self.mutations = []
        self._cos = cos or []

    async def query_data(self, query, variables=None, *, action=""):
        from backend.lib.business.connectors.base import ConnectorResult
        if query.strip().startswith("mutation"):
            self.mutations.append((action, variables))
            return ConnectorResult(ok=True, data={"updateCompany": {"id": (variables or {}).get("id")},
                                                  "createCompany": {"id": "new-co"}})
        if "companies" in query:
            return ConnectorResult(ok=True, data={"companies": {"edges": [{"node": n} for n in self._cos]}})
        return ConnectorResult(ok=True, data={})


def _upd_vars(client):
    return [v for a, v in client.mutations if a == "Update company"]


# ── unit: option-key mapping + coercion ───────────────────────────────────────
def test_option_key_maps_label_to_stored_key():
    f = _schema().obj("company").field_by_name("status")
    assert writes.option_key(f, "To Be Called") == "TO_BE_CALLED"
    assert writes.option_key(f, "to be called") == "TO_BE_CALLED"   # case-insensitive
    assert writes.option_key(f, "TO_BE_CALLED") == "TO_BE_CALLED"   # already a key
    assert writes.option_key(f, "Nonsense") is None


def test_coerce_link_field_builds_composite():
    f = _schema().obj("company").field_by_name("googleMapsLink")
    val, err = writes.coerce_value(f, "https://maps.app.goo.gl/x")
    assert err is None
    assert val == {"primaryLinkUrl": "https://maps.app.goo.gl/x", "primaryLinkLabel": "", "secondaryLinks": []}


# ── update with custom fields ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_update_company_sets_select_by_label():
    c = FakeClient(cos=[{"id": "co1", "name": "Dines"}])
    res = await writes.update_company(c, _schema(), "u", {"query": "Dines",
        "fields": {"Status": "Called", "Job Status": "Pending"}})
    assert res.ok
    data = _upd_vars(c)[0]["data"]
    assert data["status"] == "CALLED" and data["jobStatus"] == "PENDING"


@pytest.mark.asyncio
async def test_update_company_link_field_not_domain():
    c = FakeClient(cos=[{"id": "co1", "name": "Dines"}])
    res = await writes.update_company(c, _schema(), "u", {"query": "Dines",
        "fields": {"Google Maps Link": "https://maps.app.goo.gl/x"}})
    assert res.ok
    data = _upd_vars(c)[0]["data"]
    assert data["googleMapsLink"]["primaryLinkUrl"] == "https://maps.app.goo.gl/x"
    assert "domainName" not in data    # link did NOT leak into domain


@pytest.mark.asyncio
async def test_update_company_bad_option_errors_with_known():
    c = FakeClient(cos=[{"id": "co1", "name": "Dines"}])
    res = await writes.update_company(c, _schema(), "u", {"query": "Dines", "fields": {"Status": "Bogus"}})
    assert not res.ok
    assert "To Be Called" in res.error and c.mutations == []   # nothing written on bad option


# ── bulk ──────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_bulk_update_sets_field_across_records():
    c = FakeClient(cos=[{"id": "1", "name": "A"}, {"id": "2", "name": "B"}, {"id": "3", "name": "C"}])
    res = await writes.bulk_update(c, _schema(), "u", {"object_type": "company",
        "names": ["A", "B", "C"], "fields": {"Status": "To Be Called"}})
    assert res.ok and res.data["updated"] == 3
    assert all(v["data"]["status"] == "TO_BE_CALLED" for v in _upd_vars(c))


@pytest.mark.asyncio
async def test_bulk_update_reports_not_found():
    c = FakeClient(cos=[{"id": "1", "name": "A"}])
    res = await writes.bulk_update(c, _schema(), "u", {"object_type": "company",
        "names": ["ZZZ"], "fields": {"Status": "Called"}})
    assert not res.ok and "not found" in res.error.lower()


# ── re-home domain → Google Maps Link ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_rehome_moves_maps_url_and_clears_domain():
    c = FakeClient(cos=[
        {"id": "1", "name": "Dines", "domainName": {"primaryLinkUrl": "https://maps.app.goo.gl/abc"}},
        {"id": "2", "name": "RealSite", "domainName": {"primaryLinkUrl": "https://realsite.com"}},
    ])
    res = await writes.rehome_field(c, _schema(), "u", {"object_type": "company",
        "from_field": "domainName", "to_field": "Google Maps Link", "contains": "maps"})
    assert res.ok and res.data["moved"] == 1     # only the maps URL moved
    data = _upd_vars(c)[0]["data"]
    assert data["googleMapsLink"]["primaryLinkUrl"] == "https://maps.app.goo.gl/abc"
    assert data["domainName"] == {"primaryLinkUrl": "", "primaryLinkLabel": "", "secondaryLinks": []}


# ── read back ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_read_fields_returns_select_labels():
    c = FakeClient(cos=[{"id": "co1", "name": "Dines", "status": "CALLED", "jobStatus": "PENDING",
                         "googleMapsLink": {"primaryLinkUrl": "https://maps.x"}}])
    res = await writes.read_fields(c, _schema(), "u", {"object_type": "company", "query": "Dines",
        "fields": ["Status", "Job Status", "Google Maps Link"]})
    assert res.ok
    f = res.data["fields"]
    assert f["Status"] == "Called" and f["Job Status"] == "Pending"
    assert f["Google Maps Link"] == "https://maps.x"


# ── guardrails ────────────────────────────────────────────────────────────────
def test_bulk_tools_are_confirm_gated():
    from backend.routes.business.chat import WRITE_ACTIONS, CRM_WRITE_ACTIONS
    assert "twenty__bulk_update" in WRITE_ACTIONS
    assert "twenty__rehome_field" in WRITE_ACTIONS
    assert "twenty__read_fields" not in WRITE_ACTIONS     # read → no confirm
    assert "twenty__bulk_update" in CRM_WRITE_ACTIONS      # but does refresh the cockpit
