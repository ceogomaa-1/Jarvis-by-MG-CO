-- Batch 3: per-user timezone + session tracking

-- 1. Add timezone column to user_preferences (already stores per-user prefs via Jarvis user_id)
alter table user_preferences add column if not exists timezone text;

-- 2. Session tracking table (user_id is Jarvis text ID, not UUID FK to auth.users)
create table if not exists user_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id text not null,
    session_started_at timestamptz not null default now(),
    last_message_at timestamptz not null default now(),
    message_count integer not null default 0,
    is_active boolean not null default true
);

create index if not exists idx_user_sessions_user_active on user_sessions(user_id, is_active);
