-- Batch 71: CO-FOUNDER MODE
-- Initiatives become executable: approve → Jarvis's Executor agent runs the
-- plan for real through the connector tool layer, and the receipts land back
-- on the row. The Operator run also stores the Analyst's live business scan.
--
-- Backend is fully backward-compatible: it runs (degraded) without this
-- migration, and upgrades itself the moment these columns exist.

-- ── business_pending_actions: execution contract + receipts ─────────────
alter table public.business_pending_actions
  add column if not exists execution_plan jsonb,
  add column if not exists execution_result jsonb,
  add column if not exists expected_impact text,
  add column if not exists decline_reason text,
  add column if not exists executed_at timestamptz;

-- Widen the status lifecycle: pending → executing → executed / execution_failed
alter table public.business_pending_actions
  drop constraint if exists business_pending_actions_status_check;
alter table public.business_pending_actions
  add constraint business_pending_actions_status_check
  check (status in (
    'pending', 'shipped', 'discarded', 'edited', 'expired',
    'executing', 'executed', 'execution_failed'
  ));

-- Activity feed reads: executed/failed initiatives for a user, newest first
create index if not exists business_pending_actions_user_executed_idx
  on public.business_pending_actions (user_id, executed_at desc)
  where executed_at is not null;

-- ── business_operator_runs: persist the Analyst's live scan ─────────────
alter table public.business_operator_runs
  add column if not exists snapshot jsonb;
