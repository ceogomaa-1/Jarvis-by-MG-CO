-- Batch 60: CRM auto-provisioning jobs (Option A)
--
-- Tracks the per-user "create their Twenty workspace" job so onboarding can kick it
-- off in the background, the UI can show a "Setting up your CRM…" pending state, and
-- failures retry silently (flagged to admin after N attempts) without ever showing the
-- user an error. The actual workspace credentials live in crm_client_workspaces; this
-- table is just the job state machine.

create table if not exists public.crm_provisioning_jobs (
    user_id     uuid primary key,
    status      text not null default 'pending',   -- 'pending' | 'done' | 'failed'
    attempts    int  not null default 0,
    last_error  text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists crm_provisioning_jobs_status_idx
    on public.crm_provisioning_jobs (status);

-- Service-role only (the backend drives provisioning; no end-user access).
alter table public.crm_provisioning_jobs enable row level security;

-- Auto-provisioned workspaces are owned by a machine service account. Persist those
-- credentials so the backend can later mint a login token to auto-sign-in the user's
-- embedded cockpit iframe (the Phase-3 SSO piece). Service-role gated, like api_key.
alter table public.crm_client_workspaces add column if not exists service_email  text;
alter table public.crm_client_workspaces add column if not exists service_secret text;
