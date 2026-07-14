-- Batch 79: autonomy policy, quota and decision ledger
--
-- Every autonomous run is authorized before execution. The database consumes
-- monthly capacity atomically so multiple workers cannot overspend the plan.

create table if not exists public.os1_autonomy_policies (
  business_id uuid primary key references public.os1_businesses(id) on delete cascade,
  autonomy_level text not null default 'approve'
    check (autonomy_level in ('observe','recommend','approve','guardrailed')),
  kill_switch boolean not null default false,
  max_daily_external_actions int not null default 30
    check (max_daily_external_actions between 0 and 10000),
  max_workflow_cost_usd numeric not null default 5
    check (max_workflow_cost_usd between 0 and 10000),
  allowed_risk_levels jsonb not null default '["low","medium","high"]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.os1_autonomy_usage (
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  period_start date not null,
  autonomous_runs int not null default 0 check (autonomous_runs >= 0),
  external_actions int not null default 0 check (external_actions >= 0),
  cost_usd numeric not null default 0 check (cost_usd >= 0),
  updated_at timestamptz not null default now(),
  primary key (business_id, period_start)
);

create table if not exists public.os1_autonomy_ledger (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  workflow_id uuid not null references public.os1_workflows(id) on delete cascade,
  user_id uuid references auth.users(id) on delete set null,
  workflow_kind text not null,
  plan text,
  decision text not null check (decision in ('allowed','denied')),
  reason text not null,
  limits_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (workflow_id)
);

create table if not exists public.os1_external_action_usage (
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  usage_date date not null,
  actions_reserved int not null default 0 check (actions_reserved >= 0),
  updated_at timestamptz not null default now(),
  primary key (business_id, usage_date)
);

create table if not exists public.os1_external_action_reservations (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  workflow_id uuid not null references public.os1_workflows(id) on delete cascade,
  usage_date date not null,
  requested_actions int not null check (requested_actions > 0),
  decision text not null check (decision in ('allowed','denied')),
  reason text not null,
  created_at timestamptz not null default now(),
  unique (workflow_id)
);

create index if not exists os1_autonomy_ledger_business_time_idx
  on public.os1_autonomy_ledger (business_id, created_at desc);

drop trigger if exists os1_autonomy_policies_updated_at on public.os1_autonomy_policies;
create trigger os1_autonomy_policies_updated_at before update on public.os1_autonomy_policies
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_autonomy_usage_updated_at on public.os1_autonomy_usage;
create trigger os1_autonomy_usage_updated_at before update on public.os1_autonomy_usage
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_external_action_usage_updated_at on public.os1_external_action_usage;
create trigger os1_external_action_usage_updated_at before update on public.os1_external_action_usage
for each row execute function public.os1_set_updated_at();

create or replace function public.consume_os1_autonomy_run(
  p_business_id uuid,
  p_workflow_id uuid,
  p_user_id uuid,
  p_workflow_kind text,
  p_plan text,
  p_period_start date,
  p_run_limit int
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  existing_decision text;
  existing_reason text;
  used_runs int;
  allowed boolean;
  decision_reason text;
begin
  perform pg_advisory_xact_lock(
    hashtextextended(p_business_id::text || ':' || p_period_start::text, 0)
  );

  select decision, reason
    into existing_decision, existing_reason
  from public.os1_autonomy_ledger
  where workflow_id = p_workflow_id;

  if found then
    return jsonb_build_object(
      'allowed', existing_decision = 'allowed',
      'reason', existing_reason,
      'duplicate', true
    );
  end if;

  if p_run_limit <= 0 then
    allowed := false;
    decision_reason := 'plan_has_no_autonomous_capacity';
    used_runs := 0;
  else
    insert into public.os1_autonomy_usage (business_id, period_start)
    values (p_business_id, p_period_start)
    on conflict (business_id, period_start) do nothing;

    update public.os1_autonomy_usage
    set autonomous_runs = autonomous_runs + 1,
        updated_at = now()
    where business_id = p_business_id
      and period_start = p_period_start
      and autonomous_runs < p_run_limit
    returning autonomous_runs into used_runs;

    allowed := found;
    decision_reason := case when allowed then 'monthly_capacity_reserved' else 'monthly_capacity_exhausted' end;
    if not allowed then
      select autonomous_runs into used_runs
      from public.os1_autonomy_usage
      where business_id = p_business_id and period_start = p_period_start;
    end if;
  end if;

  insert into public.os1_autonomy_ledger (
    business_id, workflow_id, user_id, workflow_kind, plan,
    decision, reason, limits_snapshot
  ) values (
    p_business_id, p_workflow_id, p_user_id, p_workflow_kind, p_plan,
    case when allowed then 'allowed' else 'denied' end,
    decision_reason,
    jsonb_build_object(
      'period_start', p_period_start,
      'monthly_run_limit', p_run_limit,
      'runs_used', coalesce(used_runs, 0)
    )
  );

  return jsonb_build_object(
    'allowed', allowed,
    'reason', decision_reason,
    'duplicate', false,
    'period_start', p_period_start,
    'monthly_run_limit', p_run_limit,
    'runs_used', coalesce(used_runs, 0)
  );
end;
$$;

revoke all on function public.consume_os1_autonomy_run(uuid, uuid, uuid, text, text, date, int) from public;
grant execute on function public.consume_os1_autonomy_run(uuid, uuid, uuid, text, text, date, int) to service_role;

create or replace function public.reserve_os1_external_actions(
  p_business_id uuid,
  p_workflow_id uuid,
  p_usage_date date,
  p_requested_actions int,
  p_daily_limit int
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_catalog
as $$
declare
  existing_decision text;
  existing_reason text;
  used_actions int;
  allowed boolean;
  decision_reason text;
begin
  perform pg_advisory_xact_lock(
    hashtextextended(p_business_id::text || ':external:' || p_usage_date::text, 0)
  );

  select decision, reason into existing_decision, existing_reason
  from public.os1_external_action_reservations
  where workflow_id = p_workflow_id;
  if found then
    return jsonb_build_object(
      'allowed', existing_decision = 'allowed',
      'reason', existing_reason,
      'duplicate', true
    );
  end if;

  if p_requested_actions <= 0 or p_daily_limit <= 0 then
    allowed := false;
    decision_reason := 'daily_external_action_capacity_unavailable';
    used_actions := 0;
  else
    insert into public.os1_external_action_usage (business_id, usage_date)
    values (p_business_id, p_usage_date)
    on conflict (business_id, usage_date) do nothing;

    update public.os1_external_action_usage
    set actions_reserved = actions_reserved + p_requested_actions,
        updated_at = now()
    where business_id = p_business_id
      and usage_date = p_usage_date
      and actions_reserved + p_requested_actions <= p_daily_limit
    returning actions_reserved into used_actions;

    allowed := found;
    decision_reason := case when allowed then 'daily_external_capacity_reserved' else 'daily_external_capacity_exhausted' end;
    if not allowed then
      select actions_reserved into used_actions
      from public.os1_external_action_usage
      where business_id = p_business_id and usage_date = p_usage_date;
    end if;
  end if;

  insert into public.os1_external_action_reservations (
    business_id, workflow_id, usage_date, requested_actions, decision, reason
  ) values (
    p_business_id, p_workflow_id, p_usage_date, p_requested_actions,
    case when allowed then 'allowed' else 'denied' end, decision_reason
  );

  return jsonb_build_object(
    'allowed', allowed,
    'reason', decision_reason,
    'duplicate', false,
    'requested_actions', p_requested_actions,
    'daily_limit', p_daily_limit,
    'actions_used', coalesce(used_actions, 0)
  );
end;
$$;

revoke all on function public.reserve_os1_external_actions(uuid, uuid, date, int, int) from public;
grant execute on function public.reserve_os1_external_actions(uuid, uuid, date, int, int) to service_role;

alter table public.os1_autonomy_policies enable row level security;
alter table public.os1_autonomy_usage enable row level security;
alter table public.os1_autonomy_ledger enable row level security;
alter table public.os1_external_action_usage enable row level security;
alter table public.os1_external_action_reservations enable row level security;

drop policy if exists "members read os1 autonomy policies" on public.os1_autonomy_policies;
create policy "members read os1 autonomy policies" on public.os1_autonomy_policies
  for select to authenticated using (public.is_os1_business_member(business_id));
drop policy if exists "members read os1 autonomy usage" on public.os1_autonomy_usage;
create policy "members read os1 autonomy usage" on public.os1_autonomy_usage
  for select to authenticated using (public.is_os1_business_member(business_id));
drop policy if exists "members read os1 autonomy ledger" on public.os1_autonomy_ledger;
create policy "members read os1 autonomy ledger" on public.os1_autonomy_ledger
  for select to authenticated using (public.is_os1_business_member(business_id));
drop policy if exists "members read os1 external action usage" on public.os1_external_action_usage;
create policy "members read os1 external action usage" on public.os1_external_action_usage
  for select to authenticated using (public.is_os1_business_member(business_id));
drop policy if exists "members read os1 external action reservations" on public.os1_external_action_reservations;
create policy "members read os1 external action reservations" on public.os1_external_action_reservations
  for select to authenticated using (public.is_os1_business_member(business_id));

grant select on table public.os1_autonomy_policies to authenticated;
grant select on table public.os1_autonomy_usage to authenticated;
grant select on table public.os1_autonomy_ledger to authenticated;
grant select on table public.os1_external_action_usage to authenticated;
grant select on table public.os1_external_action_reservations to authenticated;
grant select, insert, update, delete on table public.os1_autonomy_policies to service_role;
grant select, insert, update, delete on table public.os1_autonomy_usage to service_role;
grant select, insert, update, delete on table public.os1_autonomy_ledger to service_role;
grant select, insert, update, delete on table public.os1_external_action_usage to service_role;
grant select, insert, update, delete on table public.os1_external_action_reservations to service_role;

-- Explicit Data API grants also harden Batch 76 for projects using Supabase's
-- 2026 opt-in table exposure defaults.
grant select on table public.os1_businesses to authenticated;
grant select on table public.os1_business_memberships to authenticated;
grant select on table public.os1_goals to authenticated;
grant select on table public.os1_metric_definitions to authenticated;
grant select on table public.os1_metric_observations to authenticated;
grant select on table public.os1_bottlenecks to authenticated;
grant select on table public.os1_hypotheses to authenticated;
grant select on table public.os1_initiatives to authenticated;
grant select on table public.os1_initiative_events to authenticated;
grant select, insert, update, delete on table public.os1_businesses to service_role;
grant select, insert, update, delete on table public.os1_business_memberships to service_role;
grant select, insert, update, delete on table public.os1_goals to service_role;
grant select, insert, update, delete on table public.os1_metric_definitions to service_role;
grant select, insert, update, delete on table public.os1_metric_observations to service_role;
grant select, insert, update, delete on table public.os1_bottlenecks to service_role;
grant select, insert, update, delete on table public.os1_hypotheses to service_role;
grant select, insert, update, delete on table public.os1_initiatives to service_role;
grant select, insert, update, delete on table public.os1_initiative_events to service_role;
