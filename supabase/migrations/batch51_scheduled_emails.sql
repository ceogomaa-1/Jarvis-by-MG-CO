-- Batch 51 — Scheduled email send (Feature 1: Gmail "draft now, send later")
--
-- Gmail has no native schedule-send via API, so Jarvis implements its own:
-- a row here per scheduled email, dispatched by backend/cron/scheduled_emails_cron.py
-- (APScheduler every minute + POST /api/business/email/_dispatch external pinger,
-- same pattern as personal_notes reminders).

create table if not exists public.business_scheduled_emails (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  to_email text not null,
  cc text,
  subject text not null,
  body text not null,
  attachments jsonb not null default '[]'::jsonb,   -- [{doc_id, filename, content_type}]
  send_at timestamptz not null,
  status text not null default 'pending'
    check (status in ('pending','sent','failed','cancelled')),
  error text,
  created_at timestamptz not null default now(),
  sent_at timestamptz
);

create index if not exists business_scheduled_emails_due_idx
  on public.business_scheduled_emails (send_at)
  where status = 'pending';

create index if not exists business_scheduled_emails_user_idx
  on public.business_scheduled_emails (user_id, created_at desc);

alter table public.business_scheduled_emails enable row level security;

drop policy if exists "users manage own scheduled emails" on public.business_scheduled_emails;
create policy "users manage own scheduled emails" on public.business_scheduled_emails
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "service role full access scheduled emails" on public.business_scheduled_emails;
create policy "service role full access scheduled emails" on public.business_scheduled_emails
  for all using (auth.role() = 'service_role');
