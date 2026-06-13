-- Batch 50.2 — Jarvis Notes (Personal)
--
-- 1) personal_notes — full note/reminder CRUD backing the Notes panel,
--    replacing the JSON-file storage previously used by backend/agent.py.
--    `channels_sent` tracks reminder-dispatch idempotency across the
--    in-app, chat, push, and email channels.
-- 2) push_subscriptions — browser Web Push (VAPID) subscriptions used by
--    the reminder dispatcher to deliver push notifications.

create table if not exists public.personal_notes (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  note text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  remind_at timestamptz,
  done boolean not null default false,
  done_at timestamptz,
  channels_sent jsonb not null default '[]'::jsonb
);

create index if not exists personal_notes_user_idx
  on public.personal_notes (user_id, created_at desc);

create index if not exists personal_notes_due_idx
  on public.personal_notes (remind_at)
  where done = false and remind_at is not null;

alter table public.personal_notes enable row level security;

drop policy if exists "users manage own personal notes" on public.personal_notes;
create policy "users manage own personal notes" on public.personal_notes
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access personal notes" on public.personal_notes;
create policy "service role full access personal notes" on public.personal_notes
  for all using (auth.role() = 'service_role');

-- Enable Realtime so the Notes panel can subscribe to live changes.
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'personal_notes'
  ) then
    alter publication supabase_realtime add table public.personal_notes;
  end if;
end $$;


-- ════════════════════════════════════════════════════════════════════
-- push_subscriptions — Web Push (VAPID) subscriptions for note reminders
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  endpoint text not null,
  p256dh text not null,
  auth text not null,
  created_at timestamptz not null default now(),
  unique (user_id, endpoint)
);

create index if not exists push_subscriptions_user_idx
  on public.push_subscriptions (user_id);

alter table public.push_subscriptions enable row level security;

drop policy if exists "users manage own push subscriptions" on public.push_subscriptions;
create policy "users manage own push subscriptions" on public.push_subscriptions
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access push subscriptions" on public.push_subscriptions;
create policy "service role full access push subscriptions" on public.push_subscriptions
  for all using (auth.role() = 'service_role');
