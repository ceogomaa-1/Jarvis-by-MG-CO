-- Batch 77: Rue OS1 durable workflow + event runtime
--
-- Business work must survive deploys, API restarts and duplicate schedulers.
-- Work is persisted before execution, claimed atomically with SKIP LOCKED,
-- protected by expiring leases, and retried with the same idempotency key.

alter table public.business_pending_actions
  add column if not exists source_key text;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'business_pending_actions_run_source_key'
  ) then
    alter table public.business_pending_actions
      add constraint business_pending_actions_run_source_key
      unique (operator_run_id, source_key);
  end if;
end $$;

create table if not exists public.os1_workflows (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  goal_id uuid references public.os1_goals(id) on delete set null,
  initiative_id uuid references public.os1_initiatives(id) on delete set null,
  kind text not null,
  status text not null default 'queued'
    check (status in (
      'queued','running','waiting_approval','waiting_input','waiting_schedule',
      'succeeded','failed','cancelled','dead_letter'
    )),
  priority int not null default 50 check (priority between 0 and 100),
  input jsonb not null default '{}'::jsonb,
  context jsonb not null default '{}'::jsonb,
  output jsonb,
  current_step text,
  idempotency_key text,
  run_after timestamptz not null default now(),
  attempts int not null default 0,
  max_attempts int not null default 5,
  lease_owner text,
  lease_expires_at timestamptz,
  last_error text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists os1_workflows_idempotency_idx
  on public.os1_workflows (business_id, idempotency_key);
create index if not exists os1_workflows_claim_idx
  on public.os1_workflows (status, run_after, priority, created_at)
  where status in ('queued','running');
create index if not exists os1_workflows_initiative_idx
  on public.os1_workflows (initiative_id, created_at desc)
  where initiative_id is not null;

create table if not exists public.os1_workflow_steps (
  id uuid primary key default gen_random_uuid(),
  workflow_id uuid not null references public.os1_workflows(id) on delete cascade,
  step_key text not null,
  handler text not null,
  position int not null,
  status text not null default 'pending'
    check (status in ('pending','running','waiting','succeeded','failed','skipped')),
  input jsonb not null default '{}'::jsonb,
  output jsonb,
  attempts int not null default 0,
  max_attempts int not null default 3,
  idempotency_key text,
  run_after timestamptz not null default now(),
  lease_owner text,
  lease_expires_at timestamptz,
  last_error text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workflow_id, step_key)
);

create unique index if not exists os1_workflow_steps_idempotency_idx
  on public.os1_workflow_steps (workflow_id, idempotency_key);

create table if not exists public.os1_events (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  event_type text not null,
  source text not null default 'rue',
  subject_type text,
  subject_id text,
  payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  status text not null default 'pending'
    check (status in ('pending','processing','processed','failed','dead_letter')),
  available_at timestamptz not null default now(),
  attempts int not null default 0,
  max_attempts int not null default 5,
  lease_owner text,
  lease_expires_at timestamptz,
  last_error text,
  occurred_at timestamptz not null default now(),
  processed_at timestamptz,
  created_at timestamptz not null default now()
);

create unique index if not exists os1_events_idempotency_idx
  on public.os1_events (business_id, idempotency_key);
create index if not exists os1_events_claim_idx
  on public.os1_events (status, available_at, occurred_at)
  where status in ('pending','processing');

create table if not exists public.os1_workflow_events (
  id uuid primary key default gen_random_uuid(),
  workflow_id uuid not null references public.os1_workflows(id) on delete cascade,
  event_type text not null,
  from_status text,
  to_status text,
  message text,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists os1_workflow_events_timeline_idx
  on public.os1_workflow_events (workflow_id, created_at);

drop trigger if exists os1_workflows_updated_at on public.os1_workflows;
create trigger os1_workflows_updated_at before update on public.os1_workflows
for each row execute function public.os1_set_updated_at();
drop trigger if exists os1_workflow_steps_updated_at on public.os1_workflow_steps;
create trigger os1_workflow_steps_updated_at before update on public.os1_workflow_steps
for each row execute function public.os1_set_updated_at();

-- Claim due workflows. Expired running leases are reclaimed automatically.
create or replace function public.claim_os1_workflows(
  worker_name text,
  claim_limit int default 2,
  lease_seconds int default 1800
)
returns setof public.os1_workflows
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select id
    from public.os1_workflows
    where (
      (status = 'queued' and run_after <= now())
      or (status = 'running' and lease_expires_at < now())
    )
    and attempts < max_attempts
    order by priority asc, run_after asc, created_at asc
    for update skip locked
    limit greatest(least(claim_limit, 20), 1)
  )
  update public.os1_workflows w
  set status = 'running',
      lease_owner = worker_name,
      lease_expires_at = now() + make_interval(secs => greatest(lease_seconds, 30)),
      attempts = w.attempts + 1,
      started_at = coalesce(w.started_at, now()),
      last_error = null,
      updated_at = now()
  from candidates c
  where w.id = c.id
  returning w.*;
end;
$$;

create or replace function public.claim_os1_events(
  worker_name text,
  claim_limit int default 20,
  lease_seconds int default 120
)
returns setof public.os1_events
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select id
    from public.os1_events
    where (
      (status = 'pending' and available_at <= now())
      or (status = 'processing' and lease_expires_at < now())
    )
    and attempts < max_attempts
    order by available_at asc, occurred_at asc
    for update skip locked
    limit greatest(least(claim_limit, 100), 1)
  )
  update public.os1_events e
  set status = 'processing',
      lease_owner = worker_name,
      lease_expires_at = now() + make_interval(secs => greatest(lease_seconds, 30)),
      attempts = e.attempts + 1,
      last_error = null
  from candidates c
  where e.id = c.id
  returning e.*;
end;
$$;

revoke all on function public.claim_os1_workflows(text, int, int) from public;
revoke all on function public.claim_os1_events(text, int, int) from public;
grant execute on function public.claim_os1_workflows(text, int, int) to service_role;
grant execute on function public.claim_os1_events(text, int, int) to service_role;

alter table public.os1_workflows enable row level security;
alter table public.os1_workflow_steps enable row level security;
alter table public.os1_events enable row level security;
alter table public.os1_workflow_events enable row level security;

drop policy if exists "members read os1 workflows" on public.os1_workflows;
create policy "members read os1 workflows" on public.os1_workflows
  for select to authenticated
  using (public.is_os1_business_member(business_id));
drop policy if exists "members read os1 events" on public.os1_events;
create policy "members read os1 events" on public.os1_events
  for select to authenticated
  using (public.is_os1_business_member(business_id));
drop policy if exists "members read os1 workflow steps" on public.os1_workflow_steps;
create policy "members read os1 workflow steps" on public.os1_workflow_steps
  for select to authenticated
  using (
    exists (
      select 1 from public.os1_workflows w
      where w.id = workflow_id and public.is_os1_business_member(w.business_id)
    )
  );
drop policy if exists "members read os1 workflow events" on public.os1_workflow_events;
create policy "members read os1 workflow events" on public.os1_workflow_events
  for select to authenticated
  using (
    exists (
      select 1 from public.os1_workflows w
      where w.id = workflow_id and public.is_os1_business_member(w.business_id)
    )
  );

-- New Supabase projects no longer expose public tables through the Data API
-- automatically. Runtime workers use PostgREST with the service role, while
-- authenticated clients only need read access guarded by the policies above.
grant select on table public.os1_workflows to authenticated;
grant select on table public.os1_workflow_steps to authenticated;
grant select on table public.os1_events to authenticated;
grant select on table public.os1_workflow_events to authenticated;

grant select, insert, update, delete on table public.os1_workflows to service_role;
grant select, insert, update, delete on table public.os1_workflow_steps to service_role;
grant select, insert, update, delete on table public.os1_events to service_role;
grant select, insert, update, delete on table public.os1_workflow_events to service_role;
