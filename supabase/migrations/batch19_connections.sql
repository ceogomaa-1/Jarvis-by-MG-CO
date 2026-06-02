-- Batch 19 — Connector framework persistence layer

create table if not exists public.business_connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  connector_type text not null,                      -- 'twilio' | 'stripe' | 'smtp'
  display_name text,                                  -- e.g. "Mike's Twilio (+14165551234)"
  credentials jsonb not null,                         -- {sid, auth_token, from_number} or {secret_key} or {host, port, username, password, from_email}
  status text not null default 'active'               -- 'active' | 'disabled' | 'invalid'
    check (status in ('active','disabled','invalid')),
  last_tested_at timestamptz,
  last_test_result text,                              -- 'ok' | 'failed: ...'
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, connector_type)                    -- one of each kind per user (v1 simplification)
);

create index if not exists business_connections_user_idx
  on public.business_connections (user_id);

alter table public.business_connections enable row level security;

drop policy if exists "users read own connections" on public.business_connections;
create policy "users read own connections" on public.business_connections
  for select using (auth.uid() = user_id);

drop policy if exists "users write own connections" on public.business_connections;
create policy "users write own connections" on public.business_connections
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "service role full access connections" on public.business_connections;
create policy "service role full access connections" on public.business_connections
  for all using (auth.role() = 'service_role');
