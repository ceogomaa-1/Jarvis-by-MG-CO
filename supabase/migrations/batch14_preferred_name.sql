-- Batch 14.2: preferred name for personalized address
alter table user_preferences add column if not exists preferred_name text;
