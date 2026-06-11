-- Batch 46.2 — Knowledge Base
--
-- Tracks each thing the user has fed Jarvis (pasted text, URL, PDF, image,
-- docx, csv, or a member of an uploaded zip) so the "What Jarvis knows" tab
-- can list/delete by source. The actual extracted facts live in
-- business_user_memories (category = 'knowledge_base'), linked back via
-- knowledge_source_id, so they flow through the same memory pool chat reads
-- and count toward readiness checkpoints (five_memories / deep_knowledge).

create table if not exists public.business_knowledge_sources (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  label text not null,
  source_type text not null default 'text',
  fact_count integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists business_knowledge_sources_user_idx
  on public.business_knowledge_sources (user_id, created_at desc);

alter table public.business_knowledge_sources enable row level security;

drop policy if exists "users read own knowledge sources" on public.business_knowledge_sources;
create policy "users read own knowledge sources" on public.business_knowledge_sources
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access knowledge sources" on public.business_knowledge_sources;
create policy "service role full access knowledge sources" on public.business_knowledge_sources
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- Link extracted facts back to their source (cascade delete)
-- ════════════════════════════════════════════════════════════════════
alter table public.business_user_memories
  add column if not exists knowledge_source_id uuid
    references public.business_knowledge_sources(id) on delete cascade;

create index if not exists business_user_memories_knowledge_source_idx
  on public.business_user_memories (knowledge_source_id);
