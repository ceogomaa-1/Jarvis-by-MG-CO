-- Batch 52 — Multi-account connections (GoHighLevel: up to 3 accounts/user)

alter table public.business_connections
  add column if not exists account_label text not null default 'default';

alter table public.business_connections
  drop constraint if exists business_connections_user_id_connector_type_key;

alter table public.business_connections
  add constraint business_connections_user_id_connector_type_account_label_key
  unique (user_id, connector_type, account_label);

create index if not exists business_connections_user_type_idx
  on public.business_connections (user_id, connector_type);
