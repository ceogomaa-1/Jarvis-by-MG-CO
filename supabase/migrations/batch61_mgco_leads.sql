-- Batch 61: mgcoleads — MG&CO B2B lead-generation engine
--
-- Stores scored, tiered local-business leads for cold outreach (B2B only). A "run" is
-- one industry+location search (e.g. "dental clinics in Mississauga"); each run yields
-- many leads. Keyed by the Jarvis user_id who ran it (Mohamed). Raw provider payload is
-- kept (jsonb) so re-scoring with new weights never needs a re-fetch (= API cost control).
--
-- Service-role only: the backend reads/writes with the service key. RLS is ON with no
-- policies → anon/auth roles get nothing; only the service role bypasses RLS. (Same model
-- as crm_client_workspaces.)

create table if not exists public.mgco_lead_runs (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null,

    query         text not null,               -- raw user query, e.g. "salons in downtown Toronto"
    industry      text,                         -- parsed industry, e.g. "salons"
    location      text,                         -- parsed location, e.g. "downtown Toronto"
    provider      text not null default 'google_places',
    result_count  integer not null default 0,
    api_calls     integer not null default 0,   -- provider requests spent (cost tracking)

    created_at    timestamptz not null default now()
);

create index if not exists mgco_lead_runs_user_idx on public.mgco_lead_runs (user_id, created_at desc);

create table if not exists public.mgco_leads (
    id             uuid primary key default gen_random_uuid(),
    user_id        uuid not null,
    run_id         uuid references public.mgco_lead_runs(id) on delete set null,

    -- identity / contact
    place_id       text,                         -- provider place id (dedupe key)
    name           text not null,
    category       text,
    address        text,
    phone          text,
    website        text,                         -- null = no website (a hot signal)
    rating         numeric,
    review_count   integer,
    price_level    integer,                      -- 0-4 (Google), null if unknown
    business_status text,
    has_hours      boolean not null default false,

    -- scoring (re-computable from raw + weights)
    score          integer not null default 0,
    tier           text not null default 'C',    -- A | B | C
    signals        jsonb,                         -- which signals fired (for transparency)
    why            text,                          -- one-line gap + what to pitch
    pitch          text,                          -- mapped MG&CO service(s)

    -- pipeline
    pushed_to_crm  boolean not null default false,
    crm_company_id text,                          -- Twenty company id once pushed
    raw            jsonb,                          -- full normalized provider record

    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);

create index if not exists mgco_leads_user_idx on public.mgco_leads (user_id, score desc);
create index if not exists mgco_leads_tier_idx on public.mgco_leads (user_id, tier);
-- One row per (user, place) — re-running a query re-scores in place instead of duplicating.
create unique index if not exists mgco_leads_user_place_idx
    on public.mgco_leads (user_id, place_id) where place_id is not null;

alter table public.mgco_lead_runs enable row level security;
alter table public.mgco_leads enable row level security;
