-- Batch 21 — Creation deployment status persistence
-- Adds durable deploy metadata so long Vercel builds can continue after the
-- /business/create SSE stream closes.

create table if not exists public.business_creations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text not null,
  intro text,
  user_message text not null,
  industry text,
  company_name text,
  plan jsonb not null default '[]'::jsonb,
  outputs jsonb,
  artifact_markdown text,
  artifact_format text default 'markdown',
  status text not null default 'running',
  error text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

alter table public.business_creations
  add column if not exists deployment_id text,
  add column if not exists repo_url text,
  add column if not exists expected_url text,
  add column if not exists live_url text,
  add column if not exists deployment_status text,
  add column if not exists deployment_error text;

alter table public.business_creations
  drop constraint if exists business_creations_status_check;

alter table public.business_creations
  add constraint business_creations_status_check
  check (status in ('running', 'building', 'complete', 'failed'));

create index if not exists business_creations_deployment_id_idx
  on public.business_creations (deployment_id);

create index if not exists business_creations_user_idx
  on public.business_creations (user_id, created_at desc);

create index if not exists business_creations_status_idx
  on public.business_creations (status);

alter table public.business_creations enable row level security;

drop policy if exists "users read own creations" on public.business_creations;
create policy "users read own creations" on public.business_creations
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access" on public.business_creations;
create policy "service role full access" on public.business_creations
  for all using (auth.role() = 'service_role');
