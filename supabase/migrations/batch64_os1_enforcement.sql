-- Batch 64: Actually ENFORCE the OS1 tier caps (not just define them)
--
-- Two additions, both additive and service-role only (RLS on, no policies — same model as
-- batch63). Nothing here touches Personal, grandfathered access, or existing rows' tiers.
--
-- 1) trial_cost_used — a hard API-COST ceiling for trials (replaces the message-count taste).
--    We accumulate the estimated, cache-net API cost of every trial turn here; once it reaches
--    OS1_TRIAL_COST_CAP_USD the trial is blocked until the user picks a plan. A single oversized
--    message can't breach it because trials are pinned to the cheapest model with a capped
--    per-response token budget and truncated input (see backend/lib/billing/config.py).
--
-- 2) os1_buffer_platforms — first-come record of the distinct Buffer platforms (services) a user
--    has posted to through Jarvis. Pro is capped at buffer_platform_cap (2); the first two
--    platforms a Pro user posts to become their allowed set, and the 3rd is blocked with an
--    upgrade prompt. Emperor is unlimited (cap = null) so nothing is recorded against them.

-- ── 1) Trial cost ledger ────────────────────────────────────────────────────────────────
alter table public.os1_subscriptions
    add column if not exists trial_cost_used numeric not null default 0;

-- ── 2) Buffer platform usage (Pro 2-platform cap) ───────────────────────────────────────
create table if not exists public.os1_buffer_platforms (
    id          uuid primary key default gen_random_uuid(),
    user_id     text not null,
    service     text not null,            -- Buffer channel service: twitter|instagram|facebook|...
    created_at  timestamptz not null default now()
);

-- One row per (user, platform); re-posting to an already-used platform is a no-op upsert.
create unique index if not exists os1_buffer_platforms_user_service_idx
    on public.os1_buffer_platforms (user_id, service);

alter table public.os1_buffer_platforms enable row level security;
