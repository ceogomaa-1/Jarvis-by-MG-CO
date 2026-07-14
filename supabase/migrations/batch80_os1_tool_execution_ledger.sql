-- Batch 80: exactly-once guardrail for tool side effects
--
-- A network response can be lost after an external system accepted a write.
-- The durable ledger makes that ambiguity explicit and prevents blind retries.

create table if not exists public.os1_tool_executions (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.os1_businesses(id) on delete cascade,
  workflow_id uuid not null references public.os1_workflows(id) on delete cascade,
  legacy_action_id uuid references public.business_pending_actions(id) on delete set null,
  tool_call_key text not null,
  tool_name text not null,
  input_hash text not null,
  input_snapshot jsonb not null default '{}'::jsonb,
  effect_class text not null default 'unknown'
    check (effect_class in ('read','internal_write','external_write','financial','unknown')),
  status text not null default 'prepared'
    check (status in ('prepared','running','succeeded','failed','ambiguous')),
  attempts int not null default 0 check (attempts >= 0),
  result_text text,
  error text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workflow_id, tool_call_key)
);

create index if not exists os1_tool_executions_workflow_time_idx
  on public.os1_tool_executions (workflow_id, created_at);
create index if not exists os1_tool_executions_ambiguous_idx
  on public.os1_tool_executions (business_id, status, created_at desc)
  where status = 'ambiguous';

drop trigger if exists os1_tool_executions_updated_at on public.os1_tool_executions;
create trigger os1_tool_executions_updated_at before update on public.os1_tool_executions
for each row execute function public.os1_set_updated_at();

alter table public.os1_tool_executions enable row level security;

drop policy if exists "members read os1 tool executions" on public.os1_tool_executions;
create policy "members read os1 tool executions" on public.os1_tool_executions
  for select to authenticated using (public.is_os1_business_member(business_id));

grant select on table public.os1_tool_executions to authenticated;
grant select, insert, update, delete on table public.os1_tool_executions to service_role;
