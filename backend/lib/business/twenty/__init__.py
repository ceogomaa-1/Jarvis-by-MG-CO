"""
Jarvis-owned CRM (self-hosted Twenty) integration — Phase 1.

Twenty is an env-configured SINGLE shared instance (TWENTY_API_URL + TWENTY_API_KEY),
not a per-user business_connections connector. Modules:

  client.py        — TwentyClient: GraphQL over the Core (/graphql) + Metadata (/metadata) APIs
  introspect.py    — runtime schema discovery (never hardcode field names)
  field_map.py     — GHL field type -> Twenty field type mapping
  ghl_reader.py    — read a user's GHL structure + data (read-only, via existing connector)
  schema_mirror.py — recreate GHL pipelines/stages/custom-fields/tags in Twenty
  importer.py      — idempotent, resumable import of GHL records into the mirrored structure
  views.py         — recreate the Kanban board + table views
  tools.py         — twenty__* agent tool executor

The whole feature is dormant unless TWENTY_API_URL + TWENTY_API_KEY are set.
"""
