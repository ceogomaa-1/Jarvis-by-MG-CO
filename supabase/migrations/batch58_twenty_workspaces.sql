-- Batch 58 (Phase 2): per-client Jarvis CRM workspaces
--
-- Phase 1 used ONE shared Twenty instance (env: TWENTY_API_URL/TWENTY_API_KEY).
-- Phase 2 gives each client their own data-isolated Twenty workspace (native
-- multi-workspace, reached by subdomain). This table maps a Jarvis user to the
-- workspace Jarvis should talk to on their behalf, and holds that workspace's
-- own API key so the backend resolves the right tenant per user_id.
--
-- Service-role only (the backend uses the service key; the api_key column is a
-- secret and must never be exposed to end users). RLS is ON with no policies →
-- anon/auth roles get nothing; only the service role bypasses RLS.

create table if not exists public.crm_client_workspaces (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null,

    -- Twenty identifiers
    workspace_id     text,                       -- Twenty workspace id (uuid string)
    subdomain        text,                        -- e.g. 'acme' in acme.crm.jarvismgco.com
    base_url         text not null,               -- per-workspace API base, e.g. https://acme.crm.jarvismgco.com
    api_key          text not null,               -- workspace-scoped API key (secret)

    -- bookkeeping
    display_name     text,                        -- client-facing label, e.g. "Acme Realty"
    status           text not null default 'active',   -- 'active' | 'disabled'
    branding_applied boolean not null default false,   -- Jarvis CRM defaults pushed to this workspace?

    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),

    -- One active workspace per Jarvis user (Phase 2). Relax later if a client
    -- ever needs multiple workspaces (add an account_label like business_connections).
    unique (user_id)
);

-- Fast resolution path: "which workspace do I talk to for this user_id?"
create index if not exists crm_client_workspaces_user_idx
    on public.crm_client_workspaces (user_id);

-- Subdomains are globally unique across the instance (Twenty requires it).
create unique index if not exists crm_client_workspaces_subdomain_idx
    on public.crm_client_workspaces (subdomain)
    where subdomain is not null;

alter table public.crm_client_workspaces enable row level security;
