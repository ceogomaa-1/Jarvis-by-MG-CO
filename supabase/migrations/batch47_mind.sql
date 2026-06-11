-- Batch 47 — THE MIND
--
-- Foundation for the living memory graph (Canvas 2.0): pgvector embeddings +
-- a "mind" cluster category on business_user_memories, semantic similarity
-- edges, golden synapses (cross-cluster insights), a thought-trace activity
-- log (live lighting + 24h replay), and Morning Queue → memory linkage.

create extension if not exists vector;

-- ════════════════════════════════════════════════════════════════════
-- Mind metadata on existing memories
-- ════════════════════════════════════════════════════════════════════
alter table public.business_user_memories
  add column if not exists embedding vector(1536),
  add column if not exists mind_category text
    check (mind_category in ('revenue','leads','operations','people','brand','tools','risk','general')),
  add column if not exists reference_count integer not null default 0,
  add column if not exists last_referenced_at timestamptz not null default now();


-- ════════════════════════════════════════════════════════════════════
-- Edges — semantic similarity (top-k=3 per memory, threshold ~0.75)
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_mind_edges (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  memory_a_id uuid not null references public.business_user_memories(id) on delete cascade,
  memory_b_id uuid not null references public.business_user_memories(id) on delete cascade,
  weight float not null,
  created_at timestamptz not null default now(),
  unique (memory_a_id, memory_b_id)
);

create index if not exists business_mind_edges_user_idx
  on public.business_mind_edges (user_id);

alter table public.business_mind_edges enable row level security;

drop policy if exists "users read own mind edges" on public.business_mind_edges;
create policy "users read own mind edges" on public.business_mind_edges
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access mind edges" on public.business_mind_edges;
create policy "service role full access mind edges" on public.business_mind_edges
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- Golden synapses — non-obvious cross-cluster connections
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_mind_synapses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  memory_a_id uuid not null references public.business_user_memories(id) on delete cascade,
  memory_b_id uuid not null references public.business_user_memories(id) on delete cascade,
  insight text not null,
  created_at timestamptz not null default now()
);

create index if not exists business_mind_synapses_user_idx
  on public.business_mind_synapses (user_id, created_at desc);

alter table public.business_mind_synapses enable row level security;

drop policy if exists "users read own mind synapses" on public.business_mind_synapses;
create policy "users read own mind synapses" on public.business_mind_synapses
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access mind synapses" on public.business_mind_synapses;
create policy "service role full access mind synapses" on public.business_mind_synapses
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- Thought-trace activity log — live "memory used / born" lighting + replay
-- ════════════════════════════════════════════════════════════════════
create table if not exists public.business_mind_activity (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  memory_id uuid not null references public.business_user_memories(id) on delete cascade,
  event_type text not null check (event_type in ('used', 'born')),
  conversation_id text,
  created_at timestamptz not null default now()
);

create index if not exists business_mind_activity_user_idx
  on public.business_mind_activity (user_id, created_at desc);

alter table public.business_mind_activity enable row level security;

drop policy if exists "users read own mind activity" on public.business_mind_activity;
create policy "users read own mind activity" on public.business_mind_activity
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access mind activity" on public.business_mind_activity;
create policy "service role full access mind activity" on public.business_mind_activity
  for all using (auth.role() = 'service_role');


-- ════════════════════════════════════════════════════════════════════
-- Morning Queue: link items back to the memories that spawned them
-- ════════════════════════════════════════════════════════════════════
alter table public.morning_queue_items
  add column if not exists source_memory_ids uuid[],
  add column if not exists synapse_id uuid references public.business_mind_synapses(id) on delete set null;


-- ════════════════════════════════════════════════════════════════════
-- Cosine nearest-neighbor RPC — used to build edges for a given memory
-- ════════════════════════════════════════════════════════════════════
create or replace function public.match_mind_memories(
  query_embedding vector(1536),
  match_user_id uuid,
  exclude_memory_id uuid,
  match_threshold float,
  match_count int
)
returns table (id uuid, similarity float)
language sql stable as $$
  select id, 1 - (embedding <=> query_embedding) as similarity
  from public.business_user_memories
  where user_id = match_user_id
    and id != exclude_memory_id
    and embedding is not null
    and 1 - (embedding <=> query_embedding) > match_threshold
  order by embedding <=> query_embedding
  limit match_count;
$$;
