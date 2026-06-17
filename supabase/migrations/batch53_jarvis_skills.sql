-- Batch 53 — Jarvis Skills
--
-- A user-authored skills system. The user feeds Jarvis material (paste or file);
-- Jarvis stores it WHOLE and forever, learns it, and changes how it operates.
--
-- This replaces the lossy fact-extraction path (knowledge_base.py) that discarded
-- the user's document whenever it wasn't a list of concrete facts. The full raw
-- material is the source of truth and is NEVER truncated away.
--
-- Two skill kinds:
--   knowledge — things Jarvis should know / recall / cite
--   behavior  — procedures / personality / operating rules that change how it acts
--   both      — content that does both
--
-- user_id is TEXT (the business "user_<hex>" form, also compatible with the raw
-- personal uuid string) so it matches the document_chunks store used for retrieval.

create table if not exists public.jarvis_skills (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  name text not null,
  description text not null default '',          -- the trigger: "when this skill applies"
  skill_type text not null default 'knowledge',  -- 'knowledge' | 'behavior' | 'both'
  full_content text not null,                     -- complete raw material, verbatim. Source of truth.
  operating_instructions text,                    -- for behavior skills: explicit "operate like this"
  source_type text not null default 'text',       -- text | url | pdf | docx | image | csv | md | zip-member
  source_filename text,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists jarvis_skills_user_idx
  on public.jarvis_skills (user_id, created_at desc);
create index if not exists jarvis_skills_user_enabled_idx
  on public.jarvis_skills (user_id, enabled);

alter table public.jarvis_skills enable row level security;

-- All access is server-mediated through the backend using the service-role key
-- (same pattern as document_chunks). RLS denies anon/public; service role has full
-- access. (jarvis_skills.user_id is the text business form, not an auth.uid() uuid,
-- so an auth.uid() owner policy would never match — access stays backend-only.)
drop policy if exists "service role full access jarvis skills" on public.jarvis_skills;
create policy "service role full access jarvis skills" on public.jarvis_skills
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- Reuse the existing pgvector store (document_chunks) for skill knowledge.
-- Tag chunks with the originating skill, and allow chunks that belong to a
-- skill rather than an uploaded user_document (document_id becomes nullable).
-- ════════════════════════════════════════════════════════════════════
alter table public.document_chunks add column if not exists skill_id uuid;
alter table public.document_chunks alter column document_id drop not null;

create index if not exists idx_document_chunks_skill on public.document_chunks (skill_id);

-- Skill-scoped vector similarity search (mirrors search_document_chunks, but only
-- over chunks that belong to enabled-skill knowledge for this user).
create or replace function match_skill_chunks(
    p_user_id text,
    p_embedding vector(1536),
    p_top_k int default 5
)
returns table(id uuid, skill_id uuid, content text, similarity float)
language sql stable
as $$
    select
        dc.id,
        dc.skill_id,
        dc.content,
        1 - (dc.embedding <=> p_embedding) as similarity
    from document_chunks dc
    where dc.user_id = p_user_id
      and dc.skill_id is not null
      and dc.embedding is not null
    order by dc.embedding <=> p_embedding
    limit p_top_k;
$$;
