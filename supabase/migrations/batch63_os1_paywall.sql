-- Batch 63: Jarvis OS1 paywall — tiered subscriptions + grandfathering + trial anti-abuse
--
-- Gates Jarvis OS1 (Business) behind a tiered paywall for NEW users only. Existing users
-- are grandfathered: every account that exists at deploy time is flagged grandfathered=true
-- and treated as active_subscription=true, so they pass straight into OS1 and never see
-- pricing or get charged. Currency is CAD. Additive — does not touch Personal, CRM, Leads,
-- provisioning, or the MG&CO / Property Partners RE workspaces.
--
-- Keying: user_id is the SAME app form used everywhere else — 'user_' || hex(auth uuid),
-- e.g. the frontend's `'user_' + session.user.id.replace(/-/g,'')`. The grandfather backfill
-- below computes exactly that from auth.users so existing accounts match their own rows.
--
-- Service-role only: the backend reads/writes with the service key. RLS is ON with no
-- policies → anon/auth roles get nothing; only the service role bypasses RLS. (Same model
-- as mgco_leads / crm_client_workspaces.)

-- ── Subscriptions: one row per user, source of truth for OS1 access + tier ──────────────
create table if not exists public.os1_subscriptions (
    user_id              text primary key,           -- 'user_' + hex(auth uuid)
    email                text,

    -- access
    active_subscription  boolean not null default false,  -- true while a paid/trialing sub is live
    grandfathered        boolean not null default false,  -- pre-paywall account → always passes free
    plan                 text,                            -- 'pro' | 'emperor' | null
    billing_interval     text,                            -- 'month' | 'year' | null
    status               text,                            -- stripe sub status: trialing|active|past_due|canceled|... ; 'grandfathered' for legacy

    -- trial (one extremely-limited 7-day trial per identity, card required up front)
    trial_used           boolean not null default false,  -- this identity has ever started a trial
    trial_ends_at        timestamptz,

    -- stripe linkage
    stripe_customer_id   text,
    stripe_subscription_id text,
    current_period_end   timestamptz,

    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now()
);

create index if not exists os1_subscriptions_customer_idx on public.os1_subscriptions (stripe_customer_id);
create index if not exists os1_subscriptions_sub_idx on public.os1_subscriptions (stripe_subscription_id);

alter table public.os1_subscriptions enable row level security;

-- ── Trial fingerprints: enforce ONE trial per identity (anti-abuse) ─────────────────────
-- A trial is blocked if ANY signal has been seen before: normalized email, Stripe card
-- fingerprint, or device/IP. We record a row when a trial actually starts (webhook) and
-- check these columns before granting a new one.
create table if not exists public.os1_trial_fingerprints (
    id               uuid primary key default gen_random_uuid(),
    user_id          text,
    email_normalized text,                  -- lowercased, gmail dots/plus stripped
    card_fingerprint text,                  -- Stripe PaymentMethod card.fingerprint
    ip               text,                  -- best-effort device/IP signal at checkout start
    created_at       timestamptz not null default now()
);

create index if not exists os1_trial_fp_email_idx on public.os1_trial_fingerprints (email_normalized);
create index if not exists os1_trial_fp_card_idx on public.os1_trial_fingerprints (card_fingerprint);
create index if not exists os1_trial_fp_ip_idx on public.os1_trial_fingerprints (ip);

alter table public.os1_trial_fingerprints enable row level security;

-- ── Jarvis Leads metered usage (Emperor overage — Google Places is real cash) ───────────
-- Counts billable lookups per user per billing month so the webhook/cron can report overage
-- past the Emperor allowance. Additive; the leads engine logs here, billing reads it.
create table if not exists public.os1_leads_usage (
    id            uuid primary key default gen_random_uuid(),
    user_id       text not null,
    period        text not null,            -- 'YYYY-MM' billing bucket
    lookups       integer not null default 0,
    updated_at    timestamptz not null default now()
);

create unique index if not exists os1_leads_usage_user_period_idx
    on public.os1_leads_usage (user_id, period);

alter table public.os1_leads_usage enable row level security;

-- ── GRANDFATHER BACKFILL ────────────────────────────────────────────────────────────────
-- Flag EVERY account that exists right now as grandfathered + active. This is the cutoff:
-- anyone created after this migration runs has no row here → must subscribe. Re-runnable
-- (on conflict do nothing) so it never downgrades an existing row.
insert into public.os1_subscriptions (user_id, email, active_subscription, grandfathered, plan, status)
select
    'user_' || replace(u.id::text, '-', ''),
    u.email,
    true,
    true,
    'emperor',                              -- legacy users keep full access (Leads, white-label, etc.)
    'grandfathered'
from auth.users u
on conflict (user_id) do nothing;
