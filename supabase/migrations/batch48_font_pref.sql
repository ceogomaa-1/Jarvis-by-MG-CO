-- Batch 48: readable font toggle (pixel/normal), persisted per user
alter table user_preferences add column if not exists font_pref text check (font_pref in ('pixel','normal'));
