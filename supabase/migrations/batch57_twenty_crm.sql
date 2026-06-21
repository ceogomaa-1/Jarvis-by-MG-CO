-- Batch 57: Jarvis-owned CRM (Twenty) — structure + import maps
--
-- Backs the idempotent, resumable GHL -> Twenty migration. Both tables are
-- keyed by user_id with unique constraints so re-running the importer/mirror
-- updates in place and never duplicates.

-- ghl pipeline/stage/custom-field/tag id  <->  twenty id (+ extra metadata)
create table if not exists public.crm_structure_map (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null,
    ghl_kind    text not null,            -- 'pipeline' | 'stage' | 'custom_field' | 'tag'
    ghl_id      text not null,
    twenty_id   text not null,            -- object id, field id, option value, etc.
    extra       jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    unique (user_id, ghl_kind, ghl_id)
);

create index if not exists crm_structure_map_user_idx
    on public.crm_structure_map (user_id, ghl_kind);

-- ghl record id  <->  twenty record id, per record type
create table if not exists public.crm_import_map (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null,
    ghl_id      text not null,
    twenty_id   text not null,
    record_type text not null,            -- 'person' | 'company' | 'opportunity' | 'note' | 'task'
    created_at  timestamptz not null default now(),
    unique (user_id, ghl_id, record_type)
);

create index if not exists crm_import_map_user_idx
    on public.crm_import_map (user_id, record_type);

-- Service-role only (the backend uses the service key; no end-user access).
alter table public.crm_structure_map enable row level security;
alter table public.crm_import_map enable row level security;
