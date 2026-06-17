-- Batch 55 — Study notes can hold images (Apple Notes style)
--
-- images: jsonb array of { path, name } pointing at objects in the
-- personal-chat-attachments storage bucket. Rendered via signed URLs.

alter table public.study_notes
  add column if not exists images jsonb not null default '[]'::jsonb;
