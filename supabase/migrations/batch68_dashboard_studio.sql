-- Batch 68: Dashboard Studio — Jarvis can build/edit/restyle ANY block, on real data.
--
-- Home stops being a fixed 10-block template. Users (through Jarvis, conversationally,
-- or by tapping in the grid) create their own blocks — expense lists, notes, live KPIs,
-- charts, and web-pulled news — that live in the SAME react-grid-layout alongside the
-- precomputed blocks. Theme (colors/fonts/density) lives in business_home_layout.settings.
--
-- One new table. Custom blocks are keyed by the Jarvis user_id; their grid identity is
-- "custom:<id>". Service-role only (the backend mediates every read/write); RLS on.

create table if not exists public.business_home_custom_blocks (
    id          uuid primary key default gen_random_uuid(),
    user_id     text not null,
    block_type  text not null,                       -- 'list' | 'note' | 'metric' | 'chart' | 'news'
    title       text not null default '',
    config      jsonb not null default '{}'::jsonb,  -- {chart_kind, news_topic, unit, ...}
    data        jsonb not null default '{}'::jsonb,  -- the REAL data: items[], text, metric{}, headlines[]
    style       jsonb not null default '{}'::jsonb,  -- per-block override: {accent, emphasis}
    status      text not null default 'active',      -- 'active' | 'deleted' (soft delete → undo)
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    deleted_at  timestamptz
);

create index if not exists business_home_custom_blocks_user_idx
    on public.business_home_custom_blocks (user_id, status, updated_at desc);

alter table public.business_home_custom_blocks enable row level security;
