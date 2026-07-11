# Rue CRM — self-hosted, white-labeled Twenty

This is the owned CRM. We run a **white-labeled fork of [Twenty](https://twenty.com)**
(AGPL-3.0 — commercial self-hosting approved) on our own VPS as **Rue CRM**, mirror a
client's GoHighLevel structure + data into it, and give each client their own isolated
workspace. GHL stays connected and read-only.

> This holds **real client data**. The image tag in `docker-compose.yml` is pinned and
> there is a backup plan below — follow it.

**Phase docs:**
- [`FORK.md`](./FORK.md) — fork + rebase workflow (how we stay upgradeable).
- [`branding/`](./branding/README.md) — the Rue CRM white-label overlay (dark luxury theme).
- [`AGPL-COMPLIANCE.md`](./AGPL-COMPLIANCE.md) — how we satisfy AGPL source-availability. **Read before go-live.**
- Per-client workspaces: see [§7 below](#7-per-client-workspaces-phase-2).

---

## 1. Provision a VPS

Any Ubuntu 22.04+ box with Docker works (Hetzner CX22, DigitalOcean 2GB+, etc.).
Minimum: 2 vCPU / 4 GB RAM / 40 GB disk.

```bash
# On the VPS, as a sudo user:
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER      # log out/in so docker works without sudo
```

## 2. Configure

```bash
git clone <this repo>            # or copy just the infra/twenty/ folder
cd infra/twenty
cp .env.example .env
nano .env                        # set APP_SECRET, PG_DATABASE_PASSWORD, SERVER_URL
#   APP_SECRET:           openssl rand -base64 32
#   PG_DATABASE_PASSWORD: openssl rand -base64 24
#   SERVER_URL:           https://crm.yourdomain.com   (or http://<vps-ip>:3000 to start)
```

## 3. Launch

```bash
docker compose up -d
docker compose ps                # all healthy?
docker compose logs -f server    # watch first-run migrations finish
```

Open `SERVER_URL` in a browser → create your workspace (first account becomes admin).

### TLS (production)
Put Caddy or nginx in front so the browser and the Rue backend talk HTTPS:

```caddyfile
# /etc/caddy/Caddyfile
crm.yourdomain.com {
    reverse_proxy localhost:3000
}
```

After the workspace exists, set `IS_SIGN_UP_ENABLED=false` in `.env` and
`docker compose up -d` again to stop new public signups.

## 4. Create the API key

In Twenty: **Settings → API & Webhooks → Create Key**. Copy it immediately — it's
shown once. Then set these in the **Rue backend environment** (Render/Railway, not
this `.env`):

```
TWENTY_API_URL=https://crm.yourdomain.com    # base URL — code appends /graphql and /metadata
TWENTY_API_KEY=<the key>
```

Verify Rue can see it:

```bash
python backend/scripts/import_ghl_to_twenty.py --user-id <uuid> --dry-run
# Should log the introspected Twenty schema (objects + fields).
```

## 5. Backups (do this — it's real data)

Nightly `pg_dump` to a file + offsite copy. Add to the VPS crontab (`crontab -e`):

```cron
# 03:15 daily: dump the Twenty db into a dated, gzip'd file (keep 14 days)
15 3 * * * docker compose -f /home/USER/infra/twenty/docker-compose.yml exec -T db \
  pg_dump -U twenty default | gzip > /home/USER/backups/twenty-$(date +\%F).sql.gz
30 3 * * * find /home/USER/backups -name 'twenty-*.sql.gz' -mtime +14 -delete
```

Also snapshot the `db-data` volume (or the whole VPS) on your provider's schedule.
Restore: `gunzip -c twenty-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U twenty default`.

## 6. Upgrading Twenty

1. Back up first (step 5).
2. Bump the `image:` tag in `docker-compose.yml` (both `server` and `worker`).
3. `docker compose pull && docker compose up -d` — `server` runs migrations automatically.

---

## How Rue uses this

| Env var | Meaning |
|---|---|
| `TWENTY_API_URL` | Base URL (e.g. `https://crm.yourdomain.com`). Code appends `/graphql/` (data) and `/metadata/` (schema). |
| `TWENTY_API_KEY` | Bearer token from Settings → API & Webhooks. |

When both are set, the Rue business agent gains `twenty__*` tools and the GHL→Twenty
importer (`backend/lib/business/twenty/`, run via `backend/scripts/import_ghl_to_twenty.py`)
becomes available. This single shared instance remains a valid fallback; Phase 2 adds
per-client workspaces on top (below).

---

## 7. Per-client workspaces (Phase 2)

Each client gets their **own data-isolated Twenty workspace**, reached at
`<client>.crm.jarvismgco.com`. Rue resolves the right workspace per `user_id`.

**One-time infra:**
1. Wildcard DNS `*.crm.jarvismgco.com` → the VPS, and wildcard TLS (Caddy:
   `*.crm.jarvismgco.com { reverse_proxy localhost:3000 }` with a DNS-01 cert).
2. `IS_MULTIWORKSPACE_ENABLED=true` (already in `docker-compose.yml` / `.env.example`).
3. Run the branded image (`JARVIS_CRM_IMAGE`) — see [`FORK.md`](./FORK.md).
4. Apply the Rue migration so the backend can store workspace keys:
   `supabase/migrations/batch58_twenty_workspaces.sql` (table `crm_client_workspaces`).

**Provision a new client (repeatable):**
1. In Rue CRM, create the client's workspace + pick a subdomain (e.g. `acme`).
2. In that workspace: **Settings → API & Webhooks → Create Key** (copy once).
3. Register it against the client's Rue `user_id`:
   ```bash
   python -m backend.scripts.provision_twenty_workspace \
     --user-id <uuid> \
     --base-url https://acme.crm.jarvismgco.com \
     --api-key <workspace key> \
     --display-name "Acme Realty"
   ```
   This verifies the key, applies Rue CRM defaults, and stores the mapping.
4. Import their GHL data into *their* workspace:
   `python -m backend.scripts.import_ghl_to_twenty --user-id <uuid>`
   (the importer resolves the same per-user workspace automatically).

**Isolation:** a workspace API key is scoped to one workspace, so client A's `user_id`
can never resolve client B's records. Proven in
`backend/tests/test_twenty_workspaces.py`.

| Env var (Rue backend) | Meaning |
|---|---|
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Back the `crm_client_workspaces` registry. |
| `TWENTY_API_URL` / `TWENTY_API_KEY` | Optional Phase-1 shared instance (used as fallback when a user has no workspace). |

---

## 8. CRM cockpit — embedding in Rue (Phase 3)

Rue shows the user's CRM inside the app: a **"CRM"** item in the Business menu opens a
cockpit that embeds `<client>.crm.jarvismgco.com` in an iframe with the Rue chat docked
beside it. The chat can now **read AND write** the CRM (create/update contacts &
opportunities, move stages, notes, tasks, tags). Deletes are hold-to-confirm. Writes go to
Twenty only — GHL stays read-only. After a write, the embed auto-refreshes.

**Two things must be configured for the embed (Mohamed):**

1. **Allow framing from the Rue origin.** By default Twenty may send `X-Frame-Options` /
   a restrictive CSP `frame-ancestors`, which blocks the iframe. Configure the reverse proxy
   (Caddy/nginx) in front of Twenty to set:
   ```
   Content-Security-Policy: frame-ancestors 'self' https://<jarvis-app-domain>;
   ```
   and remove any `X-Frame-Options: DENY/SAMEORIGIN`. The cockpit has an "Open in new tab"
   fallback if framing stays blocked.

2. **Avoid double login (SSO / session pass-through).** The CRM has its own session, separate
   from Rue's Supabase auth. Options, easiest first:
   - **Shared Google OAuth:** enable Google sign-in on Twenty with the same Google project, so
     a user already signed into Google is one click in. (Lowest effort.)
   - **OIDC SSO:** point Twenty's SSO at the same IdP as Rue so the iframe session is
     established transparently. (Cleanest; needs Twenty SSO config.)
   - Document whichever is chosen here once decided. ⚠️ Flag — Mohamed to pick.

The embed URL Rue uses is resolved server-side from the user's workspace
(`GET /api/business/crm/workspace`) — the SAME per-user routing the agent writes through, so
the cockpit always shows the exact tenant Rue is editing.
