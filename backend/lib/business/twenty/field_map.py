"""
GHL custom-field type -> Twenty field-metadata type mapping.

GHL (v2) reports a `dataType` on each custom field. Twenty's metadata API takes a
`type` from its FieldMetadataType enum. We map conservatively: anything we can't
faithfully represent falls back to TEXT so no data is lost (the raw value is still
stored as text).

The chosen Twenty type strings are VALIDATED against the live enum at mirror time
(see schema_mirror.resolve_field_type) — if a target type isn't supported by the
running Twenty version, we degrade to TEXT rather than fail the whole import.
"""

# Twenty types that carry a list of options (SELECT/MULTI_SELECT).
OPTION_TYPES = {"SELECT", "MULTI_SELECT"}

# GHL dataType (upper-cased) -> preferred Twenty FieldMetadataType.
# GHL dataTypes seen in the v2 API: TEXT, LARGE_TEXT, TEXTBOX_LIST, NUMERICAL,
# MONETORY, PHONE, EMAIL, DATE, CHECKBOX, SINGLE_OPTIONS, MULTIPLE_OPTIONS,
# RADIO, FILE_UPLOAD, SIGNATURE.
_GHL_TO_TWENTY: dict[str, str] = {
    "TEXT": "TEXT",
    "LARGE_TEXT": "TEXT",
    "TEXTBOX_LIST": "TEXT",
    "NUMERICAL": "NUMBER",
    "MONETORY": "CURRENCY",   # GHL's spelling
    "MONETARY": "CURRENCY",
    "PHONE": "PHONES",
    "EMAIL": "EMAILS",
    "DATE": "DATE_TIME",
    "CHECKBOX": "MULTI_SELECT",      # GHL checkbox = multiple selectable options
    "SINGLE_OPTIONS": "SELECT",
    "MULTIPLE_OPTIONS": "MULTI_SELECT",
    "RADIO": "SELECT",
    "FILE_UPLOAD": "TEXT",   # store the URL/text; real attachments are out of scope for Phase 1
    "SIGNATURE": "TEXT",
}

# Fallback used everywhere a type is unknown/unsupported.
DEFAULT_TYPE = "TEXT"


def ghl_type_to_twenty(ghl_data_type: str | None) -> str:
    """Map one GHL dataType string to a Twenty FieldMetadataType. Defaults to TEXT."""
    if not ghl_data_type:
        return DEFAULT_TYPE
    return _GHL_TO_TWENTY.get(ghl_data_type.strip().upper(), DEFAULT_TYPE)


def needs_options(twenty_type: str) -> bool:
    """True if the Twenty type requires an `options` list (SELECT / MULTI_SELECT)."""
    return twenty_type in OPTION_TYPES


def extract_ghl_options(ghl_field: dict) -> list[str]:
    """
    Pull the option labels off a GHL custom-field definition. GHL returns options
    either as a list of strings or a list of {label/value} dicts depending on type.
    """
    raw = ghl_field.get("options") or ghl_field.get("picklistOptions") or []
    out: list[str] = []
    for opt in raw:
        if isinstance(opt, str):
            label = opt
        elif isinstance(opt, dict):
            label = opt.get("label") or opt.get("name") or opt.get("value") or ""
        else:
            label = str(opt)
        label = (label or "").strip()
        if label and label not in out:
            out.append(label)
    return out
