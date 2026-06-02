-- Batch 18 — Risk Management Proactive Cron
-- Two tables: user's current metrics blob + the daily proactive briefings

-- ════════════════════════════════════════════════════════════════════
-- business_user_metrics — one row per user, holds latest natural-language metrics
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_user_metrics (
  user_id uuid primary key,
  metrics_text text not null,
  updated_at timestamptz not null default now()
);

alter table public.business_user_metrics enable row level security;

drop policy if exists "users read own metrics" on public.business_user_metrics;
create policy "users read own metrics" on public.business_user_metrics
  for select using (auth.uid() = user_id);

drop policy if exists "users write own metrics" on public.business_user_metrics;
create policy "users write own metrics" on public.business_user_metrics
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "service role full access metrics" on public.business_user_metrics;
create policy "service role full access metrics" on public.business_user_metrics
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- business_proactive_messages — one row per daily briefing
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_proactive_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  briefing_text text not null,
  flag_severity text not null default 'none'
    check (flag_severity in ('red','yellow','green','none','stale')),
  flag_summary text,
  suggested_action text,
  evaluated_flags jsonb,
  read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists business_proactive_user_idx
  on public.business_proactive_messages (user_id, created_at desc);
create index if not exists business_proactive_unread_idx
  on public.business_proactive_messages (user_id, read);

alter table public.business_proactive_messages enable row level security;

drop policy if exists "users read own briefings" on public.business_proactive_messages;
create policy "users read own briefings" on public.business_proactive_messages
  for select using (auth.uid() = user_id);

drop policy if exists "users update own briefings" on public.business_proactive_messages;
create policy "users update own briefings" on public.business_proactive_messages
  for update using (auth.uid() = user_id);

drop policy if exists "service role full access briefings" on public.business_proactive_messages;
create policy "service role full access briefings" on public.business_proactive_messages
  for all using (auth.role() = 'service_role');
