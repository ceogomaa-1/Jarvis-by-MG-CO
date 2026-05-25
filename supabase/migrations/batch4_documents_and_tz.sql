-- Batch 4: document storage + timezone confirmation flag

-- 1. Enable pgvector for semantic search
create extension if not exists vector;

-- 2. Uploaded documents index
create table if not exists user_documents (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    filename text not null,
    file_type text not null,
    file_size integer,
    chunk_count integer default 0,
    uploaded_at timestamptz not null default now()
);

create index if not exists idx_user_documents_user on user_documents(user_id);

-- 3. Document chunks with optional vector embeddings
create table if not exists document_chunks (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null references user_documents(id) on delete cascade,
    user_id text not null,
    chunk_index integer not null,
    content text not null,
    embedding vector(1536),
    created_at timestamptz not null default now()
);

create index if not exists idx_document_chunks_user on document_chunks(user_id);
create index if not exists idx_document_chunks_doc on document_chunks(document_id);

-- 4. Vector similarity search RPC
create or replace function search_document_chunks(
    p_user_id text,
    p_embedding vector(1536),
    p_top_k int default 5
)
returns table(id uuid, document_id uuid, content text, similarity float)
language sql stable
as $$
    select
        dc.id,
        dc.document_id,
        dc.content,
        1 - (dc.embedding <=> p_embedding) as similarity
    from document_chunks dc
    where dc.user_id = p_user_id
      and dc.embedding is not null
    order by dc.embedding <=> p_embedding
    limit p_top_k;
$$;

-- 5. Timezone confirmation flag on user_preferences
alter table user_preferences add column if not exists timezone text;
alter table user_preferences add column if not exists timezone_confirmed boolean default false;
