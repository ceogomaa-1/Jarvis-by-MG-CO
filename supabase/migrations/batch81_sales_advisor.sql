-- Batch 81: Sales Advisor — deep-research pitch reports
--
-- One row per analysis job: Mohamed points Rue at a specific business (Google Maps link
-- and/or name + any intel he has) and the engine deep-researches it, then generates a
-- closer-grade pitch report (offer, deck, call script, objections). The row doubles as
-- the job record: status/progress are polled by the cockpit while the detached task runs.
--
-- Service-role only: the backend reads/writes with the service key. RLS is ON with no
-- policies → anon/auth roles get nothing; only the service role bypasses RLS. (Same model
-- as mgco_leads / crm_client_workspaces.)

create table if not exists public.mgco_sales_reports (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null,

    -- input
    business_name  text not null,                -- resolved name (placeholder until research lands)
    maps_url       text,                          -- Google Maps link the user supplied, if any
    notes          text,                          -- owner-provided intel fed into the research

    -- job state (polled by the cockpit)
    status         text not null default 'running',   -- running | complete | failed
    progress       text,                               -- human-readable current stage
    error          text,

    -- payloads
    research       jsonb,                         -- full research bundle (profile, reviews, audit, site, intel)
    report         jsonb,                         -- the structured pitch report (deck, offer, objections…)
    model          text,                          -- LLM that generated the report (cost/audit trail)

    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create index if not exists mgco_sales_reports_user_idx
    on public.mgco_sales_reports (user_id, created_at desc);

alter table public.mgco_sales_reports enable row level security;
