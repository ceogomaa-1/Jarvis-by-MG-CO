"""Sales Advisor — deep-research a specific business, then produce a closer-grade,
MG&CO-grounded pitch deck for it (offer, deck, call script, objection handling).

Pipeline: resolve target (Google Maps URL / name) → Places profile + reviews →
website scrape (stealth) → web intel → deterministic digital-presence audit →
one big LLM pass that turns the research into a structured pitch report.

Additive and env-gated like mgcoleads: no key material of its own (reuses
LEADS_MAPS_API_KEY when present, degrades gracefully when not).
"""
