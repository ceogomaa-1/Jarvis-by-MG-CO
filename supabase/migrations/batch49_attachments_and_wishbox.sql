-- Batch 49 — Persistent visible chat attachments + Wish Box -> Notion
--
-- 1) business_messages.attachments — metadata for files attached to a user
--    message ([{name, media_type, size, storage_path}]), so history reloads
--    can re-render thumbnails/chips and resolve signed URLs from Storage.
--
-- 2) chat-attachments storage bucket (private) — users can read/write only
--    under their own prefix `{auth.uid()}/...`.
--
-- 3) jarvis_wishes — fallback store for the Wish Box feedback pipeline when
--    the Notion API call fails (rate limit, missing access, etc). The wish
--    is never lost and `notion_synced=false` rows can be retried later.

alter table public.business_messages
  add column if not exists attachments jsonb not null default '[]'::jsonb;


-- ════════════════════════════════════════════════════════════════════
-- chat-attachments storage bucket
-- ════════════════════════════════════════════════════════════════════
insert into storage.buckets (id, name, public)
values ('chat-attachments', 'chat-attachments', false)
on conflict (id) do nothing;

drop policy if exists "users manage own chat attachments" on storage.objects;
create policy "users manage own chat attachments"
on storage.objects for all
using (bucket_id = 'chat-attachments' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'chat-attachments' and (storage.foldername(name))[1] = auth.uid()::text);


-- ════════════════════════════════════════════════════════════════════
-- jarvis_wishes — Wish Box fallback / audit log
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.jarvis_wishes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  email text,
  wish_text text not null,
  notion_page_id text,
  notion_synced boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists jarvis_wishes_user_idx
  on public.jarvis_wishes (user_id, created_at desc);

create index if not exists jarvis_wishes_unsynced_idx
  on public.jarvis_wishes (notion_synced) where notion_synced = false;

alter table public.jarvis_wishes enable row level security;

drop policy if exists "users manage own wishes" on public.jarvis_wishes;
create policy "users manage own wishes" on public.jarvis_wishes
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "service role full access wishes" on public.jarvis_wishes;
create policy "service role full access wishes" on public.jarvis_wishes
  for all using (auth.role() = 'service_role');
