-- Batch 16 — Jarvis Business Creation 1.0 persistence
-- One row per orchestrator run. Stores plan, all sub-agent outputs, and final artifact.

create table if not exists public.business_creations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text not null,
  intro text,
  user_message text not null,
  industry text,
  company_name text,
  plan jsonb not null,          -- the orchestrator's plan (list of sub-agents)
  outputs jsonb,                 -- {agent_id: {role, task, output, ok, error?}}
  artifact_markdown text,        -- the reporter's final artifact
  artifact_format text default 'markdown',
  status text not null default 'running' check (status in ('running','complete','failed')),
  error text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists business_creations_user_idx on public.business_creations (user_id, created_at desc);
create index if not exists business_creations_status_idx on public.business_creations (status);

-- RLS
alter table public.business_creations enable row level security;

drop policy if exists "users read own creations" on public.business_creations;
create policy "users read own creations" on public.business_creations
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access" on public.business_creations;
create policy "service role full access" on public.business_creations
  for all using (auth.role() = 'service_role');
