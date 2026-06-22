"""
Step 4 — import GHL data into the mirrored Twenty structure. Idempotent + resumable.

  GHL contact      -> Person  (+ Company link, custom fields, tags)
  GHL business     -> Company
  GHL opportunity  -> Opportunity (correct pipeline stage + custom fields)
  GHL note         -> Note  (attached to the person)
  GHL task         -> Task  (attached to the person)

Idempotency: every created Twenty record is recorded in crm_import_map keyed by the
GHL id + record_type. Re-running skips anything already mapped, so a second run makes
zero new records. GHL is never written to.

Robustness across Twenty versions: record inputs are built DEFENSIVELY — a field is
only sent if the introspected object actually has it (composite shapes for
name/emails/phones/amount differ between versions). Core mutation names are derived
from the introspected `nameSingular` (createPerson, createOpportunity, …), not guessed.
"""
from backend.lib.business.twenty import ghl_reader, store
from backend.lib.business.twenty.client import TwentyClient
from backend.lib.business.twenty.introspect import TwentySchema


def _cap(name_singular: str) -> str:
    return name_singular[:1].upper() + name_singular[1:]


class StructMaps:
    """Pre-indexed structure map for fast lookups during import."""
    def __init__(self, raw: dict[tuple[str, str], dict]):
        self.pipelines: dict[str, dict] = {}     # ghl pipeline_id -> {field_name, stage_value_by_id}
        self.stages: dict[str, dict] = {}        # ghl stage_id -> {value, field_name}
        self.custom_fields: dict[str, dict] = {} # ghl field_id -> {object, field_name, type, value_by_label}
        self.tag_value_by_label: dict[str, str] = {}
        self.tag_field_name = "ghlTags"
        for (kind, ghl_id), row in raw.items():
            extra = row.get("extra") or {}
            if kind == "pipeline":
                self.pipelines[ghl_id] = {"field_name": extra.get("field_name"), "stage_value_by_id": extra.get("stage_value_by_id", {})}
            elif kind == "stage":
                self.stages[ghl_id] = {"value": row["twenty_id"], "field_name": extra.get("field_name")}
            elif kind == "custom_field":
                self.custom_fields[ghl_id] = {
                    "object": extra.get("object"), "field_name": extra.get("field_name"),
                    "type": extra.get("type"), "value_by_label": extra.get("value_by_label", {}),
                }
            elif kind == "tag":
                label = extra.get("label")
                if label:
                    self.tag_value_by_label[label] = row["twenty_id"]
                    self.tag_field_name = extra.get("field_name", self.tag_field_name)


class Importer:
    def __init__(self, client: TwentyClient, schema: TwentySchema, user_id: str, *, dry_run: bool = False, max_records: int | None = None):
        self.client = client
        self.schema = schema
        self.user_id = user_id
        self.dry_run = dry_run
        self.max_records = max_records
        self.struct: StructMaps | None = None
        self.import_map: dict[tuple[str, str], str] = {}
        self.summary = {
            "person": {"created": 0, "skipped": 0},
            "company": {"created": 0, "skipped": 0},
            "opportunity": {"created": 0, "skipped": 0},
            "note": {"created": 0, "skipped": 0},
            "task": {"created": 0, "skipped": 0},
            "errors": [],
        }

    async def _load_maps(self):
        self.struct = StructMaps(await store.load_structure_map(self.user_id))
        self.import_map = await store.load_import_map(self.user_id)

    def _mapped(self, record_type: str, ghl_id: str) -> str | None:
        return self.import_map.get((record_type, ghl_id))

    async def _create(self, alias: str, ghl_id: str, data: dict) -> str | None:
        """Create a Twenty record of `alias` and record the mapping. Returns id."""
        obj = self.schema.obj(alias)
        if not obj:
            self.summary["errors"].append(f"{alias}: object not in schema")
            return None
        if self.dry_run:
            self.summary[alias]["created"] += 1
            return f"dry-{ghl_id}"
        mutation = f"""
        mutation Create{_cap(obj.name_singular)}($data: {_cap(obj.name_singular)}CreateInput!) {{
          create{_cap(obj.name_singular)}(data: $data) {{ id }}
        }}
        """
        res = await self.client.query_data(mutation, {"data": data}, action=f"Create {alias}")
        if not res.ok:
            self.summary["errors"].append(f"{alias} {ghl_id}: {res.error}")
            return None
        rec = (res.data or {}).get(f"create{_cap(obj.name_singular)}") or {}
        new_id = rec.get("id")
        if new_id:
            self.import_map[(alias, ghl_id)] = new_id
            await store.record_import(self.user_id, ghl_id, new_id, alias)
            self.summary[alias]["created"] += 1
        return new_id

    def _has(self, alias: str, field_name: str) -> bool:
        obj = self.schema.obj(alias)
        return bool(obj and obj.field_by_name(field_name))

    # ── input builders (defensive: only set fields the object actually has) ───
    def _apply_custom_fields(self, alias: str, ghl_custom_fields: list, data: dict):
        for cf in ghl_custom_fields or []:
            spec = self.struct.custom_fields.get(cf.get("id"))
            if not spec or spec.get("object") != alias:
                continue
            fname = spec["field_name"]
            if not self._has(alias, fname):
                continue
            value = cf.get("value", cf.get("field_value"))
            vbl = spec.get("value_by_label") or {}
            if spec.get("type") == "MULTI_SELECT":
                vals = value if isinstance(value, list) else [value]
                data[fname] = [vbl.get(str(v), str(v)) for v in vals if v]
            elif spec.get("type") == "SELECT":
                data[fname] = vbl.get(str(value), str(value)) if value else None
            elif value not in (None, ""):
                data[fname] = value

    def _person_input(self, contact: dict, company_id: str | None) -> dict:
        data: dict = {}
        if self._has("person", "name"):
            data["name"] = {
                "firstName": contact.get("firstName") or contact.get("firstNameLowerCase") or "",
                "lastName": contact.get("lastName") or contact.get("lastNameLowerCase") or "",
            }
        if self._has("person", "emails") and contact.get("email"):
            data["emails"] = {"primaryEmail": contact["email"], "additionalEmails": []}
        if self._has("person", "phones") and contact.get("phone"):
            data["phones"] = {"primaryPhoneNumber": contact["phone"], "primaryPhoneCountryCode": "", "primaryPhoneCallingCode": ""}
        if self._has("person", "city") and contact.get("city"):
            data["city"] = contact["city"]
        if self._has("person", "jobTitle") and contact.get("companyName"):
            data["jobTitle"] = contact.get("title", "")
        if company_id and self._has("person", "company"):
            data["companyId"] = company_id
        # tags
        tag_field = self.struct.tag_field_name
        if contact.get("tags") and self._has("person", tag_field):
            data[tag_field] = [self.struct.tag_value_by_label.get(t, t) for t in contact["tags"]]
        self._apply_custom_fields("person", contact.get("customFields") or contact.get("customField"), data)
        return data

    def _opportunity_input(self, opp: dict, person_id: str | None) -> dict:
        data: dict = {}
        if self._has("opportunity", "name"):
            data["name"] = opp.get("name") or "Opportunity"
        if self._has("opportunity", "amount") and opp.get("monetaryValue") is not None:
            try:
                data["amount"] = {"amountMicros": int(float(opp["monetaryValue"]) * 1_000_000), "currencyCode": "USD"}
            except (TypeError, ValueError):
                pass
        # stage: which field + which option value
        pipe = self.struct.pipelines.get(opp.get("pipelineId"))
        stage_id = opp.get("pipelineStageId") or opp.get("stageId")
        if pipe and pipe.get("field_name") and stage_id:
            value = (pipe.get("stage_value_by_id") or {}).get(stage_id) or (self.struct.stages.get(stage_id) or {}).get("value")
            if value and self._has("opportunity", pipe["field_name"]):
                data[pipe["field_name"]] = value
        if person_id and self._has("opportunity", "pointOfContact"):
            data["pointOfContactId"] = person_id
        self._apply_custom_fields("opportunity", opp.get("customFields"), data)
        return data

    # ── attach a Note/Task to a Person via the target join object ─────────────
    async def _attach_target(self, target_obj_alias: str, parent_id: str, person_id: str):
        """Best-effort: create noteTarget/taskTarget linking the record to the person.

        The join objects aren't in the introspected core set, so the mutation name is
        fixed by convention (NoteTarget/TaskTarget)."""
        if self.dry_run:
            return
        cap = _cap(target_obj_alias)   # noteTarget -> NoteTarget
        key = target_obj_alias.replace("Target", "")  # note / task
        mutation = f"""
        mutation Create{cap}($data: {cap}CreateInput!) {{ create{cap}(data: $data) {{ id }} }}
        """
        # Twenty's join FK is target{Person,...}Id, not personId.
        await self.client.query_data(
            mutation, {"data": {f"{key}Id": parent_id, "targetPersonId": person_id}}, action=f"Attach {target_obj_alias}"
        )

    # ── per-type import ───────────────────────────────────────────────────────
    async def import_companies(self, ghl):
        for biz in await ghl_reader.list_businesses(ghl):
            ghl_id = biz.get("id")
            if not ghl_id:
                continue
            if self._mapped("company", ghl_id):
                self.summary["company"]["skipped"] += 1
                continue
            data = {}
            if self._has("company", "name"):
                data["name"] = biz.get("name") or "Company"
            await self._create("company", ghl_id, data)

    async def import_contacts(self, ghl):
        async for contact in ghl_reader.iter_contacts(ghl, max_records=self.max_records):
            cid = contact.get("id")
            if not cid:
                continue
            person_id = self._mapped("person", cid)
            if person_id:
                self.summary["person"]["skipped"] += 1
            else:
                company_id = None  # GHL contact->business link is rarely populated; left for Phase 2
                person_id = await self._create("person", cid, self._person_input(contact, company_id))
            if not person_id:
                continue
            await self._import_contact_notes(ghl, cid, person_id)
            await self._import_contact_tasks(ghl, cid, person_id)

    async def _import_contact_notes(self, ghl, contact_id: str, person_id: str):
        for note in await ghl_reader.get_contact_notes(ghl, contact_id):
            nid = note.get("id")
            if not nid or self._mapped("note", nid):
                if nid:
                    self.summary["note"]["skipped"] += 1
                continue
            data = {}
            body_text = note.get("body") or ""
            if self._has("note", "title"):
                data["title"] = (note.get("body") or "Note")[:60]
            if self._has("note", "body"):
                data["body"] = body_text
            elif self._has("note", "bodyV2"):
                data["bodyV2"] = {"markdown": body_text}
            new_id = await self._create("note", nid, data)
            if new_id and not str(new_id).startswith("dry-"):
                await self._attach_target("noteTarget", new_id, person_id)

    async def _import_contact_tasks(self, ghl, contact_id: str, person_id: str):
        for task in await ghl_reader.get_contact_tasks(ghl, contact_id):
            tid = task.get("id")
            if not tid or self._mapped("task", tid):
                if tid:
                    self.summary["task"]["skipped"] += 1
                continue
            data = {}
            if self._has("task", "title"):
                data["title"] = task.get("title") or "Task"
            if self._has("task", "body"):
                data["body"] = task.get("body") or ""
            elif self._has("task", "bodyV2"):
                data["bodyV2"] = {"markdown": task.get("body") or ""}
            if self._has("task", "dueAt") and task.get("dueDate"):
                data["dueAt"] = task["dueDate"]
            new_id = await self._create("task", tid, data)
            if new_id and not str(new_id).startswith("dry-"):
                await self._attach_target("taskTarget", new_id, person_id)

    async def import_opportunities(self, ghl, structure: dict):
        for pipe in structure.get("pipelines", []):
            async for opp in ghl_reader.iter_opportunities(ghl, pipe["id"], max_records=self.max_records):
                oid = opp.get("id")
                if not oid:
                    continue
                if self._mapped("opportunity", oid):
                    self.summary["opportunity"]["skipped"] += 1
                    continue
                contact = opp.get("contact") or {}
                person_id = self._mapped("person", contact.get("id")) if contact.get("id") else None
                await self._create("opportunity", oid, self._opportunity_input(opp, person_id))

    async def run(self, ghl, structure: dict) -> dict:
        await self._load_maps()
        await self.import_companies(ghl)
        await self.import_contacts(ghl)         # people first (opps + targets reference them)
        await self.import_opportunities(ghl, structure)
        return self.summary
