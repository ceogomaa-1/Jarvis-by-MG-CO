-- Batch 62: mgcoleads — capture lead geo-coordinates for the Leads cockpit map
--
-- The Leads cockpit now plots each scored lead as a Google Map marker, so we persist the
-- lat/lng that the Google Places API already returns (places.location). Additive: nullable
-- columns, existing rows stay valid (older leads simply won't have a pin until re-discovered).
-- Re-running a query backfills coords in place (engine re-scores existing rows by place_id).

alter table public.mgco_leads add column if not exists lat numeric;
alter table public.mgco_leads add column if not exists lng numeric;
