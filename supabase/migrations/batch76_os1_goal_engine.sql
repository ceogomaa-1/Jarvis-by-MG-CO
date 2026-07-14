-- Batch 76: Rue OS1 Goal Engine + initiative control plane
--
-- The legacy North Star is a label injected into prompts. These tables turn it
-- into durable operating state: a business owns goals, goals own measurements,
-- bottlenecks and hypotheses explain the gap, and initiatives carry work through
-- execution and measurement. Existing Operator tables remain untouched and are
-- linked through operator_run_id / legacy_action_id during the migration period.

create or replace function public.os1_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- A business, not a user, is the OS1 tenancy boundary. One owner may eventually
-- operate multiple businesses; is_primary preserves today's one-business UX.
create table if not exists public.os1_businesses (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'My business',
  timezone text not null default 'America/Toronto',
  is_primary boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists os1_businesses_primary_owner_idx
  on public.os1_businesses (owner_user_id) where is_primary;

create table if not exists public.os1_business_memberships (
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'owner'
    check (role in ('owner','admin','operator','viewer')),
  created_at timestamptz not null default now(),
  primary key (business_id, user_id)
);

-- SECURITY DEFINER avoids recursive membership-policy evaluation while keeping
-- every business-scoped table protected by the same contract.
create or replace function public.is_os1_business_member(target_business_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.os1_business_memberships m
    where m.business_id = target_business_id
      and m.user_id = auth.uid()
  );
$$;

create table if not exists public.os1_goals (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  objective text not null,
  metric_key text not null,
  unit text not null default 'count',
  direction text not null default 'increase'
    check (direction in ('increase','decrease')),
  baseline_value numeric not null default 0,
  current_value numeric not null default 0,
  target_value numeric not null,
  start_at timestamptz not null default now(),
  deadline timestamptz not null,
  status text not null default 'active'
    check (status in ('draft','active','paused','achieved','missed','cancelled')),
  confidence numeric not null default 0.5 check (confidence between 0 and 1),
  constraints jsonb not null default '[]'::jsonb,
  leading_indicators jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (target_value <> baseline_value)
);

create index if not exists os1_goals_business_status_idx
  on public.os1_goals (business_id, status, deadline);
create unique index if not exists os1_goals_one_active_metric_idx
  on public.os1_goals (business_id, metric_key) where status = 'active';

create table if not exists public.os1_metric_definitions (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  metric_key text not null,
  label text not null,
  unit text not null default 'count',
  aggregation text not null default 'latest'
    check (aggregation in ('latest','sum','average','minimum','maximum')),
  source_type text not null default 'manual',
  source_config jsonb not null default '{}'::jsonb,
  freshness_minutes int,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (business_id, metric_key)
);

create table if not exists public.os1_metric_observations (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  metric_definition_id uuid not null references public.os1_metric_definitions(id) on delete cascade,
  goal_id uuid references public.os1_goals(id) on delete set null,
  value numeric not null,
  observed_at timestamptz not null default now(),
  source_type text not null default 'manual',
  source_ref text,
  idempotency_key text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists os1_metric_observations_idempotency_idx
  on public.os1_metric_observations (business_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists os1_metric_observations_metric_time_idx
  on public.os1_metric_observations (metric_definition_id, observed_at desc);

create table if not exists public.os1_bottlenecks (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  goal_id uuid not null references public.os1_goals(id) on delete cascade,
  title text not null,
  evidence text not null,
  severity int not null default 50 check (severity between 0 and 100),
  confidence numeric not null default 0.5 check (confidence between 0 and 1),
  status text not null default 'active'
    check (status in ('candidate','active','resolved','dismissed','superseded')),
  detected_by text not null default 'operator',
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists os1_bottlenecks_goal_status_idx
  on public.os1_bottlenecks (goal_id, status, severity desc);
create unique index if not exists os1_bottlenecks_one_active_goal_idx
  on public.os1_bottlenecks (goal_id) where status = 'active';

create table if not exists public.os1_hypotheses (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  goal_id uuid not null references public.os1_goals(id) on delete cascade,
  bottleneck_id uuid references public.os1_bottlenecks(id) on delete set null,
  statement text not null,
  rationale text,
  expected_effect jsonb not null default '{}'::jsonb,
  confidence numeric not null default 0.5 check (confidence between 0 and 1),
  status text not null default 'untested'
    check (status in ('untested','testing','supported','rejected','inconclusive')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.os1_initiatives (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  goal_id uuid not null references public.os1_goals(id) on delete cascade,
  bottleneck_id uuid references public.os1_bottlenecks(id) on delete set null,
  hypothesis_id uuid references public.os1_hypotheses(id) on delete set null,
  operator_run_id uuid references public.business_operator_runs(id) on delete set null,
  legacy_action_id uuid references public.business_pending_actions(id) on delete set null,
  title text not null,
  rationale text,
  expected_impact text,
  plan jsonb not null default '{}'::jsonb,
  success_criteria jsonb not null default '[]'::jsonb,
  risk_level text not null default 'medium'
    check (risk_level in ('low','medium','high','critical')),
  status text not null default 'discovered'
    check (status in (
      'discovered','qualified','planned','needs_information','needs_approval',
      'approved','scheduled','executing','blocked','verifying','measuring',
      'completed','succeeded','failed','inconclusive','cancelled'
    )),
  priority int not null default 50 check (priority between 0 and 100),
  actual_result jsonb,
  measurement_starts_at timestamptz,
  measurement_ends_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (legacy_action_id)
);

create index if not exists os1_initiatives_goal_status_idx
  on public.os1_initiatives (goal_id, status, priority, created_at desc);

-- Append-only decision/execution ledger. It is the audit trail and the future
-- learning source; rows are never edited by product code.
create table if not exists public.os1_initiative_events (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  initiative_id uuid not null references public.os1_initiatives(id) on delete cascade,
  event_type text not null,
  from_status text,
  to_status text,
  actor_type text not null default 'system'
    check (actor_type in ('user','rue','system','connector')),
  actor_id text,
  reason text,
  evidence jsonb not null default '{}'::jsonb,
  cost_usd numeric not null default 0,
  idempotency_key text,
  created_at timestamptz not null default now()
);

create unique index if not exists os1_initiative_events_idempotency_idx
  on public.os1_initiative_events (initiative_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists os1_initiative_events_timeline_idx
  on public.os1_initiative_events (initiative_id, created_at);

-- Updated-at triggers are deliberately explicit so migrations remain readable.
drop trigger if exists os1_businesses_updated_at on public.os1_businesses;
create trigger os1_businesses_updated_at before update on public.os1_businesses
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_goals_updated_at on public.os1_goals;
create trigger os1_goals_updated_at before update on public.os1_goals
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_metric_definitions_updated_at on public.os1_metric_definitions;
create trigger os1_metric_definitions_updated_at before update on public.os1_metric_definitions
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_bottlenecks_updated_at on public.os1_bottlenecks;
create trigger os1_bottlenecks_updated_at before update on public.os1_bottlenecks
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_hypotheses_updated_at on public.os1_hypotheses;
create trigger os1_hypotheses_updated_at before update on public.os1_hypotheses
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_initiatives_updated_at on public.os1_initiatives;
create trigger os1_initiatives_updated_at before update on public.os1_initiatives
for each row execute function public.os1_set_updated_at();

-- Row-level security. The backend service role performs autonomous work; users
-- receive direct read access only to businesses they belong to.
alter table public.os1_businesses enable row level security;
alter table public.os1_business_memberships enable row level security;
alter table public.os1_goals enable row level security;
alter table public.os1_metric_definitions enable row level security;
alter table public.os1_metric_observations enable row level security;
alter table public.os1_bottlenecks enable row level security;
alter table public.os1_hypotheses enable row level security;
alter table public.os1_initiatives enable row level security;
alter table public.os1_initiative_events enable row level security;

drop policy if exists "owners read own os1 businesses" on public.os1_businesses;
create policy "owners read own os1 businesses" on public.os1_businesses
  for select using (owner_user_id = auth.uid() or public.is_os1_business_member(id));
drop policy if exists "users read own os1 memberships" on public.os1_business_memberships;
create policy "users read own os1 memberships" on public.os1_business_memberships
  for select using (user_id = auth.uid());

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'os1_goals','os1_metric_definitions','os1_metric_observations',
    'os1_bottlenecks','os1_hypotheses','os1_initiatives','os1_initiative_events'
  ]
  loop
    execute format('drop policy if exists "members read %1$s" on public.%1$I', table_name);
    execute format(
      'create policy "members read %1$s" on public.%1$I for select using (public.is_os1_business_member(business_id))',
      table_name
    );
  end loop;
end $$;

-- Service-role policies make the intended authority explicit even though the
-- Supabase service role already bypasses RLS.
do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'os1_businesses','os1_business_memberships','os1_goals',
    'os1_metric_definitions','os1_metric_observations','os1_bottlenecks',
    'os1_hypotheses','os1_initiatives','os1_initiative_events'
  ]
  loop
    execute format('drop policy if exists "service role manages %1$s" on public.%1$I', table_name);
    execute format(
      'create policy "service role manages %1$s" on public.%1$I for all using (auth.role() = ''service_role'') with check (auth.role() = ''service_role'')',
      table_name
    );
  end loop;
end $$;
