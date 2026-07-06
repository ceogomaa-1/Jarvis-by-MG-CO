-- Batch 75 — Dump Learn (Jarvis Personal, Study Mode)
--
-- A "bin" the user dumps raw study material into (PDFs, docx/pptx, articles,
-- YouTube links, pasted text, images). Jarvis parses everything down to lean
-- text FIRST (token optimization happens at ingest, not at explain-time), then
-- explains it back at a user-chosen comprehension level (child/graduate/expert),
-- with the explanation cached per (bin, level) so re-picking a level or
-- reopening a bin never re-bills an LLM call.
--
-- Fully separate from study_notes/study_chats AND from jarvis_skills/
-- document_chunks — Dump Learn material must never leak into Business or
-- Personal memory retrieval, so it gets its own chunk/embedding table rather
-- than reusing document_chunks.

-- ════════════════════════════════════════════════════════════════════
-- dump_learn_bins — one "bin box" session
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.dump_learn_bins (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  title text not null default 'New bin',
  level text not null default 'graduate',   -- 'child' | 'graduate' | 'expert'
  status text not null default 'open',      -- 'open' | 'archived'
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists dump_learn_bins_user_idx
  on public.dump_learn_bins (user_id, updated_at desc);

alter table public.dump_learn_bins enable row level security;

drop policy if exists "users manage own dump learn bins" on public.dump_learn_bins;
create policy "users manage own dump learn bins" on public.dump_learn_bins
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access dump learn bins" on public.dump_learn_bins;
create policy "service role full access dump learn bins" on public.dump_learn_bins
  for all using (auth.role() = 'service_role');

-- ════════════════════════════════════════════════════════════════════
-- dump_learn_items — one dumped source (file / url / youtube / pasted text)
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.dump_learn_items (
  id uuid primary key default gen_random_uuid(),
  bin_id uuid not null references public.dump_learn_bins(id) on delete cascade,
  user_id text not null,
  kind text not null,                        -- pdf | docx | pptx | url | youtube | image | text
  source_name text,
  source_url text,
  storage_path text,                         -- Supabase Storage path, when uploaded as a file
  status text not null default 'pending',    -- pending | parsing | ready | error
  extracted_text text,                       -- lossless canonical text — the source of truth
  skeleton_md text,                          -- condensed outline (large items only)
  original_size_bytes int not null default 0, -- for the shrink-o-meter (file uploads only)
  raw_char_count int not null default 0,
  token_estimate int not null default 0,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists dump_learn_items_bin_idx
  on public.dump_learn_items (bin_id, created_at asc);
create index if not exists dump_learn_items_user_idx
  on public.dump_learn_items (user_id);
create index if not exists dump_learn_items_status_idx
  on public.dump_learn_items (status);

alter table public.dump_learn_items enable row level security;

drop policy if exists "users manage own dump learn items" on public.dump_learn_items;
create policy "users manage own dump learn items" on public.dump_learn_items
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access dump learn items" on public.dump_learn_items;
create policy "service role full access dump learn items" on public.dump_learn_items
  for all using (auth.role() = 'service_role');

-- ════════════════════════════════════════════════════════════════════
-- dump_learn_chunks — pgvector retrieval store, DELIBERATELY its own table
-- (not document_chunks) so this material can never surface in Business/
-- Personal memory retrieval. Backend-only; no direct frontend reads.
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.dump_learn_chunks (
  id uuid primary key default gen_random_uuid(),
  item_id uuid not null references public.dump_learn_items(id) on delete cascade,
  user_id text not null,
  chunk_index int not null default 0,
  content text not null,
  embedding vector(1536),
  created_at timestamptz not null default now()
);

create index if not exists dump_learn_chunks_item_idx
  on public.dump_learn_chunks (item_id, chunk_index);

alter table public.dump_learn_chunks enable row level security;

drop policy if exists "service role full access dump learn chunks" on public.dump_learn_chunks;
create policy "service role full access dump learn chunks" on public.dump_learn_chunks
  for all using (auth.role() = 'service_role');

-- Bin-scoped vector similarity search (mirrors match_skill_chunks from batch53),
-- restricted to a single item so the reasoning pass only pulls the chunks that
-- belong to the sources actually in play.
create or replace function match_dump_learn_chunks(
    p_item_id uuid,
    p_embedding vector(1536),
    p_top_k int default 6
)
returns table(id uuid, item_id uuid, content text, similarity float)
language sql stable
as $$
    select
        dlc.id,
        dlc.item_id,
        dlc.content,
        1 - (dlc.embedding <=> p_embedding) as similarity
    from dump_learn_chunks dlc
    where dlc.item_id = p_item_id
      and dlc.embedding is not null
    order by dlc.embedding <=> p_embedding
    limit p_top_k;
$$;

-- ════════════════════════════════════════════════════════════════════
-- dump_learn_explanations — cached lesson output per (bin, level, sources).
-- source_fingerprint changes whenever the bin's items change, so a stale
-- explanation is never served after new material is added.
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.dump_learn_explanations (
  id uuid primary key default gen_random_uuid(),
  bin_id uuid not null references public.dump_learn_bins(id) on delete cascade,
  user_id text not null,
  level text not null,                     -- child | graduate | expert
  source_fingerprint text not null,        -- hash of the bin's ready item ids + updated_at
  tldr text not null default '',
  sections_json jsonb not null default '[]'::jsonb,
  mind_map_json jsonb,
  quiz_json jsonb not null default '[]'::jsonb,
  model_used text,
  cost_usd numeric(10,5),
  created_at timestamptz not null default now()
);

create unique index if not exists dump_learn_explanations_cache_idx
  on public.dump_learn_explanations (bin_id, level, source_fingerprint);

alter table public.dump_learn_explanations enable row level security;

drop policy if exists "users manage own dump learn explanations" on public.dump_learn_explanations;
create policy "users manage own dump learn explanations" on public.dump_learn_explanations
  for all
  using (('user_' || replace(auth.uid()::text, '-', '')) = user_id)
  with check (('user_' || replace(auth.uid()::text, '-', '')) = user_id);

drop policy if exists "service role full access dump learn explanations" on public.dump_learn_explanations;
create policy "service role full access dump learn explanations" on public.dump_learn_explanations
  for all using (auth.role() = 'service_role');

-- ════════════════════════════════════════════════════════════════════
-- dump-learn-uploads storage bucket (private) — same convention as
-- personal-chat-attachments (batch50): users read/write only their own
-- {auth.uid()}/... prefix; the backend downloads via the service-role key
-- to parse file bytes in the background ingest task.
-- ════════════════════════════════════════════════════════════════════
insert into storage.buckets (id, name, public)
values ('dump-learn-uploads', 'dump-learn-uploads', false)
on conflict (id) do nothing;

drop policy if exists "users manage own dump learn uploads" on storage.objects;
create policy "users manage own dump learn uploads"
on storage.objects for all
using (bucket_id = 'dump-learn-uploads' and (storage.foldername(name))[1] = auth.uid()::text)
with check (bucket_id = 'dump-learn-uploads' and (storage.foldername(name))[1] = auth.uid()::text);
