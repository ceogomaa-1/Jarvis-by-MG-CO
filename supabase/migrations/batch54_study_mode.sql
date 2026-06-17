-- Batch 54 — Study Mode (Jarvis Personal)
--
-- Study Mode has its OWN storage, fully separate from personal_notes / normal
-- chat history:
--   1) study_notes  — captured notes, grouped by category, shown in the Study
--      drawer (the hamburger menu while in Study Mode).
--   2) study_chats  — multiple study conversations per user (new-chat support),
--      messages stored as a JSONB array on the chat row.

-- ════════════════════════════════════════════════════════════════════
-- study_notes — captured study notes (categorized)
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.study_notes (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  content text not null,
  category text not null default 'General',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists study_notes_user_idx
  on public.study_notes (user_id, created_at desc);

alter table public.study_notes enable row level security;

drop policy if exists "users manage own study notes" on public.study_notes;
create policy "users manage own study notes" on public.study_notes
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access study notes" on public.study_notes;
create policy "service role full access study notes" on public.study_notes
  for all using (auth.role() = 'service_role');

-- ════════════════════════════════════════════════════════════════════
-- study_chats — multiple study conversations (new-chat support)
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.study_chats (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  title text not null default 'New chat',
  messages jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists study_chats_user_idx
  on public.study_chats (user_id, updated_at desc);

alter table public.study_chats enable row level security;

drop policy if exists "users manage own study chats" on public.study_chats;
create policy "users manage own study chats" on public.study_chats
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access study chats" on public.study_chats;
create policy "service role full access study chats" on public.study_chats
  for all using (auth.role() = 'service_role');
