-- Batch 67: Jarvis Home — the adaptive AI workspace.
--
-- Home is a fast READ over a precomputed cache. The Operator pipeline's new final
-- step ("compose_home") writes living, actionable blocks here nightly; the view never
-- fires a chain of LLM calls on page load. Four tables:
--   business_home_blocks      — the precomputed block cache (one row per user × block)
--   business_home_layout      — per-user react-grid-layout JSON + Home settings
--   business_home_usage       — telemetry (views, click-throughs, first-action order, dwell)
--   business_home_suggestions — Phase 3 adaptive reorg proposals (suggestion-only)
--
-- All tables are keyed by the Jarvis user_id ('user_' prefixed). Service-role only;
-- the backend mediates every read/write, so RLS is enabled with no public policy.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Precomputed block cache
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.business_home_blocks (
    id                uuid primary key default gen_random_uuid(),
    user_id           text not null,
    block_key         text not null,           -- e.g. 'daily_briefing', 'biggest_risk'
    title             text not null default '',
    ai_summary        text not null default '', -- explains the change/risk/opportunity
    evidence          jsonb not null default '[]'::jsonb,   -- [{label, value}]
    primary_action    jsonb,                    -- {label, kind, prompt|tool_name|target, ...}
    secondary_actions jsonb not null default '[]'::jsonb,
    score             numeric not null default 0,           -- urgency×value×risk×recency
    score_breakdown   jsonb not null default '{}'::jsonb,   -- {urgency,value,risk,recency,weights}
    status            text not null default 'ok',           -- 'ok' | 'empty' | 'needs_connection'
    operator_run_id   uuid,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    unique (user_id, block_key)
);

create index if not exists business_home_blocks_user_idx
    on public.business_home_blocks (user_id, score desc);

alter table public.business_home_blocks enable row level security;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Per-user layout + Home settings
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.business_home_layout (
    id          uuid primary key default gen_random_uuid(),
    user_id     text not null unique,
    -- react-grid-layout `layouts` keyed by breakpoint, plus a `blocks` map of
    -- { block_key: { visible, ... } }. Shape owned by the frontend/home_layout lib.
    layout      jsonb not null default '{}'::jsonb,
    -- Home settings: { default_landing: bool, ... }
    settings    jsonb not null default '{"default_landing": true}'::jsonb,
    is_default  boolean not null default true,        -- false once the user customizes
    updated_at  timestamptz not null default now()
);

alter table public.business_home_layout enable row level security;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Telemetry (collected from day one; consumed by Phase 3)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.business_home_usage (
    id          uuid primary key default gen_random_uuid(),
    user_id     text not null,
    block_key   text,                                  -- null for whole-Home events
    event_type  text not null,                         -- 'view' | 'click_through' | 'first_action' | 'dwell'
    position    integer,                               -- order index (first-action ordering)
    dwell_ms    integer,
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists business_home_usage_user_idx
    on public.business_home_usage (user_id, created_at desc);
create index if not exists business_home_usage_user_event_idx
    on public.business_home_usage (user_id, event_type);

alter table public.business_home_usage enable row level security;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Phase 3 adaptive suggestions (suggestion-only; never auto-applies)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists public.business_home_suggestions (
    id              uuid primary key default gen_random_uuid(),
    user_id         text not null,
    message         text not null default '',          -- "I noticed you always open CRM → Leads → Calendar…"
    proposed_layout jsonb,                              -- the reorg to apply on accept
    evidence        jsonb not null default '{}'::jsonb, -- {pattern, sample_size, ...}
    status          text not null default 'pending',    -- 'pending' | 'accepted' | 'rejected'
    created_at      timestamptz not null default now(),
    resolved_at     timestamptz
);

create index if not exists business_home_suggestions_user_idx
    on public.business_home_suggestions (user_id, status, created_at desc);

alter table public.business_home_suggestions enable row level security;
