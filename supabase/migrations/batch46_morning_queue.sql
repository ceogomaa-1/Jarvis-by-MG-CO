-- Batch 46.3 — Morning Queue
--
-- Daily proactive digest. Generated once per day (Render Cron ->
-- POST /business/morning-queue/generate-all) for every "active" user
-- (operator_enabled = true OR readiness score >= 60). Each item is one of
-- suggestion / draft / warning / opportunity, surfaced in the Morning Queue
-- panel with unread badges on the hamburger + menu item.

create table if not exists public.morning_queue_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  date date not null default current_date,
  type text not null check (type in ('suggestion', 'draft', 'warning', 'opportunity')),
  title text not null,
  body text not null,
  action_prompt text,
  read boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists morning_queue_items_user_date_idx
  on public.morning_queue_items (user_id, date desc, created_at desc);

alter table public.morning_queue_items enable row level security;

drop policy if exists "users read own morning queue items" on public.morning_queue_items;
create policy "users read own morning queue items" on public.morning_queue_items
  for select using (auth.uid() = user_id);

drop policy if exists "users update own morning queue items" on public.morning_queue_items;
create policy "users update own morning queue items" on public.morning_queue_items
  for update using (auth.uid() = user_id);

drop policy if exists "service role full access morning queue items" on public.morning_queue_items;
create policy "service role full access morning queue items" on public.morning_queue_items
  for all using (auth.role() = 'service_role');
