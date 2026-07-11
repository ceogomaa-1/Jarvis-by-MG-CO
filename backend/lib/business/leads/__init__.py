"""mgcoleads — MG&CO's B2B lead-generation engine inside Rue.

Pipeline: query → provider ingest (Google Places, swappable adapter) → score (0-100,
A/B/C) → persist → surface in chat → push to the Rue CRM. B2B only (local businesses
MG&CO sells to). Additive + env-gated (see config.leads_enabled)."""
