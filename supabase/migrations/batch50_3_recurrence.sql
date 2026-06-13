-- Batch 50.3 — Recurring reminders for Jarvis Notes (Personal)
--
-- Adds remind_recurrence to personal_notes so a fired reminder can re-arm
-- itself (daily/weekly/monthly) instead of staying fired forever.
-- backend/cron/notes_reminders.py computes the next remind_at (timezone
-- correct, via the user's saved timezone) and resets channels_sent to '[]'
-- once every channel has dispatched.
--
-- This column is already live in production; this migration exists for
-- repo parity / fresh environments and is safe to re-run.

alter table public.personal_notes
  add column if not exists remind_recurrence text not null default 'none';

alter table public.personal_notes
  drop constraint if exists personal_notes_remind_recurrence_check;

alter table public.personal_notes
  add constraint personal_notes_remind_recurrence_check
  check (remind_recurrence in ('none', 'daily', 'weekly', 'monthly'));
