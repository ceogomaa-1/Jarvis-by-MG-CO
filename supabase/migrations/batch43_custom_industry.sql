-- Batch 43 — Cinematic onboarding: support free-text "Other" industries
alter table public.business_users add column if not exists custom_industry text;
