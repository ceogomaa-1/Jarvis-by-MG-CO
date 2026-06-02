-- Batch 20 — Brand customization, North Star tracking, Operator Agent

-- ════════════════════════════════════════════════════════════════════
-- business_brand_config — per-user brand + North Star target
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_brand_config (
  user_id uuid primary key,
  logo_url text,
  banner_url text,
  accent_color text default '#c84b31',
  display_name text,
  north_star_target_usd numeric default 1000000,
  north_star_target_label text default '$1M ARR',
  operator_enabled boolean not null default false,
  operator_daily_budget_usd numeric not null default 5.00,
  updated_at timestamptz not null default now()
);

alter table public.business_brand_config enable row level security;

drop policy if exists "users read own brand" on public.business_brand_config;
create policy "users read own brand" on public.business_brand_config
  for select using (auth.uid() = user_id);

drop policy if exists "users write own brand" on public.business_brand_config;
create policy "users write own brand" on public.business_brand_config
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "service role full access brand" on public.business_brand_config;
create policy "service role full access brand" on public.business_brand_config
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- business_operator_runs — one row per nightly run per user
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_operator_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  status text not null default 'running'
    check (status in ('running','complete','failed','budget_capped','skipped')),
  cycles_completed int not null default 0,
  total_cost_usd numeric not null default 0,
  strategist_output jsonb,
  researcher_output jsonb,
  creator_outputs jsonb,
  packager_output jsonb,
  error text,
  started_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists business_operator_runs_user_idx
  on public.business_operator_runs (user_id, started_at desc);

alter table public.business_operator_runs enable row level security;

drop policy if exists "users read own runs" on public.business_operator_runs;
create policy "users read own runs" on public.business_operator_runs
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access runs" on public.business_operator_runs;
create policy "service role full access runs" on public.business_operator_runs
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- business_pending_actions — the morning approval queue
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_pending_actions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  operator_run_id uuid references public.business_operator_runs(id) on delete cascade,
  action_type text not null,
  title text not null,
  description text,
  internal_or_external text not null default 'internal'
    check (internal_or_external in ('internal','external')),
  artifact_markdown text,
  artifact_metadata jsonb,
  connector_type text,
  priority int not null default 50,
  status text not null default 'pending'
    check (status in ('pending','shipped','discarded','edited','expired')),
  shipped_at timestamptz,
  shipped_result jsonb,
  created_at timestamptz not null default now()
);

create index if not exists business_pending_actions_user_status_idx
  on public.business_pending_actions (user_id, status, priority);
create index if not exists business_pending_actions_run_idx
  on public.business_pending_actions (operator_run_id);

alter table public.business_pending_actions enable row level security;

drop policy if exists "users read own actions" on public.business_pending_actions;
create policy "users read own actions" on public.business_pending_actions
  for select using (auth.uid() = user_id);

drop policy if exists "users update own actions" on public.business_pending_actions;
create policy "users update own actions" on public.business_pending_actions
  for update using (auth.uid() = user_id);

drop policy if exists "service role full access actions" on public.business_pending_actions;
create policy "service role full access actions" on public.business_pending_actions
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- Storage bucket for logo + banner uploads
-- ════════════════════════════════════════════════════════════════════
insert into storage.buckets (id, name, public)
values ('business-brand-assets', 'business-brand-assets', true)
on conflict (id) do nothing;

drop policy if exists "users upload own brand assets" on storage.objects;
create policy "users upload own brand assets" on storage.objects
  for insert with check (
    bucket_id = 'business-brand-assets'
    and auth.role() = 'authenticated'
  );

drop policy if exists "public read brand assets" on storage.objects;
create policy "public read brand assets" on storage.objects
  for select using (bucket_id = 'business-brand-assets');

drop policy if exists "users update own brand assets" on storage.objects;
create policy "users update own brand assets" on storage.objects
  for update using (
    bucket_id = 'business-brand-assets'
    and auth.role() = 'authenticated'
  );

drop policy if exists "users delete own brand assets" on storage.objects;
create policy "users delete own brand assets" on storage.objects
  for delete using (
    bucket_id = 'business-brand-assets'
    and auth.role() = 'authenticated'
  );
