-- Batch 72: THE DETECTIVE + owner notifications
-- 1) business_cofounder_questions — Jarvis asks the owner the questions that
--    unlock better moves (strategist gaps + executor NEEDs). Answers become
--    standing facts the Analyst feeds into every future scan.
-- 2) business_owner_notifications — durable ledger enforcing the
--    max-2-per-day owner notification cap (in-app + Resend email).

-- ── Detective questions ──────────────────────────────────────────────
create table if not exists public.business_cofounder_questions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  operator_run_id uuid references public.business_operator_runs(id) on delete set null,
  action_id uuid references public.business_pending_actions(id) on delete set null,
  source text not null default 'strategist'
    check (source in ('strategist','executor')),
  question text not null,
  why_it_matters text,
  unlocks text,
  status text not null default 'open'
    check (status in ('open','answered','dismissed')),
  answer text,
  answered_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists business_cofounder_questions_user_status_idx
  on public.business_cofounder_questions (user_id, status, created_at desc);

alter table public.business_cofounder_questions enable row level security;

drop policy if exists "users read own questions" on public.business_cofounder_questions;
create policy "users read own questions" on public.business_cofounder_questions
  for select using (auth.uid() = user_id);

drop policy if exists "users update own questions" on public.business_cofounder_questions;
create policy "users update own questions" on public.business_cofounder_questions
  for update using (auth.uid() = user_id);

drop policy if exists "service role full access questions" on public.business_cofounder_questions;
create policy "service role full access questions" on public.business_cofounder_questions
  for all using (auth.role() = 'service_role');

-- ── Owner notification ledger (the 2/day cap) ────────────────────────
create table if not exists public.business_owner_notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  kind text not null,
  subject text,
  channel text not null default 'inapp',
  dedupe_key text,
  created_at timestamptz not null default now()
);

create index if not exists business_owner_notifications_user_day_idx
  on public.business_owner_notifications (user_id, created_at desc);

alter table public.business_owner_notifications enable row level security;

drop policy if exists "users read own notifications" on public.business_owner_notifications;
create policy "users read own notifications" on public.business_owner_notifications
  for select using (auth.uid() = user_id);

drop policy if exists "service role full access notifications" on public.business_owner_notifications;
create policy "service role full access notifications" on public.business_owner_notifications
  for all using (auth.role() = 'service_role');
