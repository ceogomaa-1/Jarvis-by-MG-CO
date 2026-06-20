-- Batch 56 — "What's New" feature announcements (in-app + email blast)
--
-- A single shared announcements system surfaced in BOTH Jarvis Personal and
-- Jarvis OS1 (Business). When Mohamed publishes a feature, every user (a) sees
-- an animated in-app "What's New" card the next time they open Jarvis, and
-- (b) gets one branded email about it.
--
-- 1) announcements             — the feature notes themselves (markdown body).
-- 2) user_announcements_seen   — per-user/per-announcement "seen" rows; drives
--                                the unread badge and stops the modal re-popping.
-- 3) announcement_email_log    — one row per announcement once its email blast
--                                has run, so re-publishing never double-emails.

-- ════════════════════════════════════════════════════════════════════
-- announcements
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.announcements (
  id            uuid primary key default gen_random_uuid(),
  title         text not null,
  body          text not null,                         -- markdown
  tag           text not null default 'New Feature',   -- 'New Feature' | 'Improvement' | 'Fix'
  media_url     text,                                  -- optional image / gif / lottie URL
  cta_label     text,
  cta_url       text,
  is_published  boolean not null default false,
  published_at  timestamptz,
  created_at    timestamptz not null default now()
);

create index if not exists announcements_published_idx
  on public.announcements (is_published, published_at desc);

alter table public.announcements enable row level security;

-- Any authenticated user can read published announcements.
drop policy if exists "authenticated read published announcements" on public.announcements;
create policy "authenticated read published announcements" on public.announcements
  for select using (auth.role() = 'authenticated' and is_published = true);

-- Service role (backend) has full access for authoring / publishing.
drop policy if exists "service role full access announcements" on public.announcements;
create policy "service role full access announcements" on public.announcements
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- user_announcements_seen — per-user seen state (unread badge + history)
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.user_announcements_seen (
  user_id         text not null,
  announcement_id uuid not null references public.announcements (id) on delete cascade,
  seen_at         timestamptz not null default now(),
  unique (user_id, announcement_id)
);

create index if not exists user_announcements_seen_user_idx
  on public.user_announcements_seen (user_id);

alter table public.user_announcements_seen enable row level security;

-- A user manages only their own seen rows. user_id is stored as text (the app
-- uses both the raw uuid and the "user_<hex>" business form), so we compare
-- against both shapes of auth.uid().
drop policy if exists "users manage own seen rows" on public.user_announcements_seen;
create policy "users manage own seen rows" on public.user_announcements_seen
  for all using (
    user_id = auth.uid()::text
    or user_id = 'user_' || replace(auth.uid()::text, '-', '')
  ) with check (
    user_id = auth.uid()::text
    or user_id = 'user_' || replace(auth.uid()::text, '-', '')
  );

drop policy if exists "service role full access seen rows" on public.user_announcements_seen;
create policy "service role full access seen rows" on public.user_announcements_seen
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- announcement_email_log — idempotency guard for the email blast
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.announcement_email_log (
  announcement_id  uuid primary key references public.announcements (id) on delete cascade,
  sent_at          timestamptz not null default now(),
  recipients_count integer not null default 0
);

alter table public.announcement_email_log enable row level security;

drop policy if exists "service role full access email log" on public.announcement_email_log;
create policy "service role full access email log" on public.announcement_email_log
  for all using (auth.role() = 'service_role') with check (auth.role() = 'service_role');
