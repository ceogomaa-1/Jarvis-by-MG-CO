-- Batch 65: Jarvis OS1 reachable on messaging channels (Telegram now, WhatsApp phase 2)
--
-- Lets an authenticated OS1 subscriber chat the SAME OS1 business brain from Telegram (and,
-- behind a flag, WhatsApp) — text + media, conversational only (no CRM cockpit / web controls).
-- Gated exactly like the web app: only users with has_access (active OR grandfathered) can
-- link, so ALL currently-grandfathered users get this immediately for free, and only new users
-- are gated. Additive + service-role only (RLS on, no policies — same model as batch63/64).
-- Does NOT touch Personal or the web app.
--
-- Keying: user_id is the SAME app form used everywhere else — 'user_' || hex(auth uuid).

-- ── Channel links: a messaging identity ⇄ an OS1 user ───────────────────────────────────
-- One row per (channel, channel_user_id). channel_user_id is the Telegram chat id or the
-- WhatsApp phone number (E.164). A user may link multiple channels; a given channel identity
-- maps to exactly one user.
create table if not exists public.os1_channel_links (
    id                uuid primary key default gen_random_uuid(),
    user_id           text not null,                 -- 'user_' + hex(auth uuid)
    channel           text not null,                 -- 'telegram' | 'whatsapp'
    channel_user_id   text not null,                 -- telegram chat id / whatsapp phone (E.164)
    channel_username  text,                          -- @handle / display name, best-effort
    created_at        timestamptz not null default now(),
    last_seen_at      timestamptz
);

create unique index if not exists os1_channel_links_identity_idx
    on public.os1_channel_links (channel, channel_user_id);
create index if not exists os1_channel_links_user_idx
    on public.os1_channel_links (user_id);

alter table public.os1_channel_links enable row level security;

-- ── One-time link codes (generated in the web app, redeemed from the channel DM) ─────────
create table if not exists public.os1_channel_link_codes (
    id                uuid primary key default gen_random_uuid(),
    code              text not null unique,          -- short, human-typeable
    user_id           text not null,                 -- who generated it (must have has_access)
    channel           text not null default 'telegram',
    created_at        timestamptz not null default now(),
    expires_at        timestamptz not null,
    used_at           timestamptz,                   -- null until redeemed
    channel_user_id   text                           -- filled in on redemption
);

create index if not exists os1_channel_link_codes_user_idx
    on public.os1_channel_link_codes (user_id);

alter table public.os1_channel_link_codes enable row level security;

-- ── Per-link conversation history (so the channel chat has context) ──────────────────────
-- Kept separate from business_conversations/business_messages so it never pollutes the web
-- app's conversation list. Only a short recent window is loaded into each turn.
create table if not exists public.os1_channel_messages (
    id          uuid primary key default gen_random_uuid(),
    link_id     uuid not null references public.os1_channel_links (id) on delete cascade,
    role        text not null,                       -- 'user' | 'assistant'
    content     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists os1_channel_messages_link_idx
    on public.os1_channel_messages (link_id, created_at);

alter table public.os1_channel_messages enable row level security;
