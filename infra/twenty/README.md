# Jarvis-owned CRM — self-hosted Twenty (Phase 1)

This is the owned CRM foundation. We run [Twenty](https://twenty.com) (open-source,
AGPL — commercial use approved for this project) on our own VPS, then mirror a client's
GoHighLevel structure + data into it. GHL stays connected and read-only.

> This holds **real client data**. The image tag in `docker-compose.yml` is pinned and
> there is a backup plan below — follow it.

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
Put Caddy or nginx in front so the browser and the Jarvis backend talk HTTPS:

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
shown once. Then set these in the **Jarvis backend environment** (Render/Railway, not
this `.env`):

```
TWENTY_API_URL=https://crm.yourdomain.com    # base URL — code appends /graphql and /metadata
TWENTY_API_KEY=<the key>
```

Verify Jarvis can see it:

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

## How Jarvis uses this

| Env var | Meaning |
|---|---|
| `TWENTY_API_URL` | Base URL (e.g. `https://crm.yourdomain.com`). Code appends `/graphql/` (data) and `/metadata/` (schema). |
| `TWENTY_API_KEY` | Bearer token from Settings → API & Webhooks. |

When both are set, the Jarvis business agent gains `twenty__*` tools and the GHL→Twenty
importer (`backend/lib/business/twenty/`, run via `backend/scripts/import_ghl_to_twenty.py`)
becomes available. Twenty is a single shared instance in Phase 1; per-client workspaces
come in Phase 2 (white-label fork).
