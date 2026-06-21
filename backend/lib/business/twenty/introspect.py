"""
Runtime schema introspection for Twenty — the "no guessing" layer.

Everything downstream (schema_mirror, importer, views, tools) resolves real object
ids / field names through here instead of hardcoding them, because:
  - custom objects/fields are runtime data in Twenty, not compiled types, and
  - exact metadata shapes drift between Twenty versions.

Two things are discovered:
  1. The metadata object catalog (id, nameSingular, namePlural, fields) for the
     built-ins we need: Person, Company, Opportunity, Note, Task.
  2. The FieldMetadataType enum the running server actually accepts (so we can
     validate/degrade target field types).

`log_schema()` prints a concise dump on first connect — that's the Step-2
"log the real object + field names" requirement and our deploy-time safety net.
"""
from dataclasses import dataclass, field

from backend.lib.business.connectors.base import ConnectorResult
from backend.lib.business.twenty.client import TwentyClient

# The built-in objects we mirror into, keyed by a stable internal alias.
# Values are the candidate `nameSingular` spellings to match case-insensitively.
TARGET_OBJECTS: dict[str, tuple[str, ...]] = {
    "person": ("person",),
    "company": ("company",),
    "opportunity": ("opportunity",),
    "note": ("note",),
    "task": ("task",),
}

_OBJECTS_QUERY = """
query Objects($after: String) {
  objects(paging: { first: 100, after: $after }) {
    edges {
      node {
        id
        nameSingular
        namePlural
        labelSingular
        labelPlural
        isCustom
        isActive
        fields(paging: { first: 200 }) {
          edges {
            node { id name label type isCustom isActive options }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

_FIELD_TYPE_ENUM_QUERY = """
query FieldTypeEnum {
  __type(name: "FieldMetadataType") { enumValues { name } }
}
"""


@dataclass
class TwentyField:
    id: str
    name: str
    label: str
    type: str
    is_custom: bool
    options: list[dict] = field(default_factory=list)


@dataclass
class TwentyObject:
    id: str
    name_singular: str
    name_plural: str
    label_singular: str
    fields: list[TwentyField] = field(default_factory=list)

    def field_by_name(self, name: str) -> TwentyField | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def field_by_type(self, type_name: str) -> TwentyField | None:
        for f in self.fields:
            if f.type == type_name:
                return f
        return None


@dataclass
class TwentySchema:
    objects: dict[str, TwentyObject]          # internal alias -> object (person, company, ...)
    field_types: set[str]                     # accepted FieldMetadataType values

    def obj(self, alias: str) -> TwentyObject | None:
        return self.objects.get(alias)

    def supports_type(self, type_name: str) -> bool:
        # If we couldn't read the enum, don't block — assume the type is fine.
        return (not self.field_types) or (type_name in self.field_types)


def _normalize_field(node: dict) -> TwentyField:
    opts = node.get("options")
    if isinstance(opts, dict):  # some versions wrap options
        opts = opts.get("options") or []
    return TwentyField(
        id=node.get("id", ""),
        name=node.get("name", ""),
        label=node.get("label", ""),
        type=node.get("type", ""),
        is_custom=bool(node.get("isCustom")),
        options=opts or [],
    )


async def fetch_objects(client: TwentyClient) -> ConnectorResult:
    """Page through the metadata object catalog. Returns list[dict] of raw nodes."""
    nodes: list[dict] = []
    after: str | None = None
    for _ in range(20):  # hard page cap
        res = await client.query_meta(_OBJECTS_QUERY, {"after": after}, action="List Twenty objects")
        if not res.ok:
            return res
        conn = (res.data or {}).get("objects") or {}
        for edge in conn.get("edges") or []:
            node = edge.get("node") or {}
            field_nodes = ((node.get("fields") or {}).get("edges")) or []
            node["_fields"] = [e.get("node") or {} for e in field_nodes]
            nodes.append(node)
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    return ConnectorResult(ok=True, data=nodes)


async def fetch_field_type_enum(client: TwentyClient) -> set[str]:
    """Discover accepted FieldMetadataType values. Empty set if introspection is off."""
    res = await client.query_meta(_FIELD_TYPE_ENUM_QUERY, action="Read FieldMetadataType enum")
    if not res.ok:
        return set()
    t = (res.data or {}).get("__type") or {}
    return {v.get("name") for v in (t.get("enumValues") or []) if v.get("name")}


async def introspect(client: TwentyClient) -> ConnectorResult:
    """
    Build a TwentySchema: resolve the built-in objects + their fields, plus the
    accepted field-type enum. Returns ConnectorResult(data=TwentySchema).
    """
    obj_res = await fetch_objects(client)
    if not obj_res.ok:
        return obj_res
    raw_objects: list[dict] = obj_res.data or []

    by_alias: dict[str, TwentyObject] = {}
    for alias, candidates in TARGET_OBJECTS.items():
        wanted = {c.lower() for c in candidates}
        match = next(
            (o for o in raw_objects if (o.get("nameSingular") or "").lower() in wanted),
            None,
        )
        if not match:
            continue
        by_alias[alias] = TwentyObject(
            id=match.get("id", ""),
            name_singular=match.get("nameSingular", ""),
            name_plural=match.get("namePlural", ""),
            label_singular=match.get("labelSingular", ""),
            fields=[_normalize_field(n) for n in match.get("_fields", [])],
        )

    field_types = await fetch_field_type_enum(client)
    schema = TwentySchema(objects=by_alias, field_types=field_types)

    missing = [a for a in TARGET_OBJECTS if a not in by_alias]
    if missing:
        return ConnectorResult(
            ok=False,
            error=(
                "Twenty schema introspection could not find built-in objects: "
                f"{', '.join(missing)}. Found objects: "
                f"{', '.join(sorted((o.get('nameSingular') or '?') for o in raw_objects))}."
            ),
            data=schema,
        )
    return ConnectorResult(ok=True, data=schema)


def log_schema(schema: TwentySchema) -> str:
    """Human-readable dump of the discovered schema (printed + returned)."""
    lines = ["TWENTY SCHEMA (introspected):"]
    for alias, obj in schema.objects.items():
        lines.append(f"  [{alias}] {obj.name_singular}/{obj.name_plural} (id={obj.id[:8]}...) — {len(obj.fields)} fields")
        for f in obj.fields:
            custom = " (custom)" if f.is_custom else ""
            lines.append(f"      - {f.name}: {f.type}{custom}")
    if schema.field_types:
        lines.append(f"  field types accepted: {', '.join(sorted(schema.field_types))}")
    out = "\n".join(lines)
    print(out)
    return out
