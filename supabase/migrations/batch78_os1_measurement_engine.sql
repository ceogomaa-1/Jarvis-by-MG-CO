-- Batch 78: outcome measurement and experiment ledger
--
-- Execution is not success. This layer records the baseline, target, window,
-- observations and honest attribution confidence for every measuring initiative.

alter table public.os1_initiatives
  add column if not exists baseline_snapshot jsonb not null default '{}'::jsonb,
  add column if not exists outcome_score numeric,
  add column if not exists attribution_confidence numeric
    check (attribution_confidence is null or attribution_confidence between 0 and 1),
  add column if not exists evaluated_at timestamptz;

create table if not exists public.os1_experiments (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  goal_id uuid not null references public.os1_goals(id) on delete cascade,
  initiative_id uuid not null references public.os1_initiatives(id) on delete cascade,
  hypothesis_id uuid references public.os1_hypotheses(id) on delete set null,
  primary_metric_key text not null,
  target_operator text not null check (target_operator in ('>=','<=','=')),
  target_value numeric not null,
  baseline_value numeric,
  baseline_observed_at timestamptz,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  status text not null default 'running'
    check (status in ('planned','running','won','lost','inconclusive','cancelled')),
  latest_value numeric,
  absolute_delta numeric,
  relative_delta numeric,
  sample_count int not null default 0,
  attribution_confidence numeric not null default 0
    check (attribution_confidence between 0 and 1),
  evaluation jsonb not null default '{}'::jsonb,
  evaluated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (initiative_id),
  check (ends_at > starts_at)
);

create index if not exists os1_experiments_due_idx
  on public.os1_experiments (status, ends_at)
  where status = 'running';
create index if not exists os1_experiments_metric_idx
  on public.os1_experiments (business_id, goal_id, primary_metric_key, status);

drop trigger if exists os1_experiments_updated_at on public.os1_experiments;
create trigger os1_experiments_updated_at before update on public.os1_experiments
for each row execute function public.os1_set_updated_at();

alter table public.os1_experiments enable row level security;

drop policy if exists "members read os1 experiments" on public.os1_experiments;
create policy "members read os1 experiments" on public.os1_experiments
  for select to authenticated
  using (public.is_os1_business_member(business_id));

grant select on table public.os1_experiments to authenticated;
grant select, insert, update, delete on table public.os1_experiments to service_role;
