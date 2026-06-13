-- Batch 50.1 — Persistent visible chat attachments (Personal)
--
-- 1) conversations.attachments — metadata for files attached to a user
--    message ([{name, media_type, size, storage_path}]), so history reloads
--    can re-render thumbnails/chips and resolve signed URLs from Storage.
--
-- 2) personal-chat-attachments storage bucket (private) — users can read/write
--    only under their own prefix `{auth.uid()}/...`.

alter table public.conversations
  add column if not exists attachments jsonb not null default '[]'::jsonb;


-- ════════════════════════════════════════════════════════════════════
-- personal-chat-attachments storage bucket
-- ════════════════════════════════════════════════════════════════════
insert into storage.buckets (id, name, public)
values ('personal-chat-attachments', 'personal-chat-attachments', false)
on conflict (id) do nothing;

drop policy if exists "users manage own personal chat attachments" on storage.objects;
create policy "users manage own personal chat attachments"
on storage.objects for all
using (bucket_id = 'personal-chat-attachments' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'personal-chat-attachments' and (storage.foldername(name))[1] = auth.uid()::text);
