# Auto-provisioning per-user CRM workspaces (Option A)

Goal: a brand-new Jarvis user finishes onboarding → the backend programmatically creates
their **own isolated Twenty workspace** + an API key, stores it, and the CRM button lights up.

This is **Option A** (proven feasible — the API supports the full flow
`signUp → signUpInNewWorkspace → getAuthTokensFromLoginToken → activateWorkspace →
createApiKey → generateApiKeyToken`). It is currently **blocked by instance config**: a probe
returned `"New workspace setup is disabled"`. The steps below unblock it. **Nothing here is
optional — without all of it, isolation is not real.**

---

## 1. Twenty env flags (on the VPS, `infra/twenty/.env`, then `docker compose up -d`)

```bash
# Multi-tenant: each client gets their own workspace, reached by subdomain.
IS_MULTIWORKSPACE_ENABLED=true

# Allow the programmatic signUp flow to create workspaces.
IS_SIGN_UP_ENABLED=true
AUTH_PASSWORD_ENABLED=true

# The service signUp must return usable tokens immediately — no email click, no captcha.
IS_EMAIL_VERIFICATION_REQUIRED=false
# (Do NOT set any CAPTCHA_* vars — captcha must stay off for the service path.)

# Base URL workspaces hang off of. Subdomains derive from this.
SERVER_URL=https://crm.jarvismgco.com
FRONTEND_BASE_URL=https://crm.jarvismgco.com
```

> Security note: `IS_SIGN_UP_ENABLED=true` also permits public signup at the apex domain.
> If you want to keep public signup closed, gate it at the proxy (allow `signUp` only from the
> Jarvis backend IP) — ask and I'll write the Caddy matcher. The service accounts Jarvis
> creates use random strong passwords on a `crm+<id>@jarvismgco.com` address; end users never
> log in with them.

## 2. Wildcard DNS

Add an A record (and AAAA if you use IPv6) for the wildcard **and** the apex:

```
*.crm.jarvismgco.com   A   <your VPS IP>
crm.jarvismgco.com     A   <your VPS IP>
```

## 3. TLS — on-demand, no DNS plugin (Hostinger)

DNS is **Hostinger**, and Caddy is the stock apt build (no DNS plugins), so we use
**on-demand TLS**: each subdomain's cert is issued on first request via HTTP-01/TLS-ALPN —
no wildcard cert, no DNS-01, no API token. Caddy "asks" the Jarvis backend before issuing a
cert, so certs are only minted for real provisioned workspaces (anti-abuse), and the apex
(where new-workspace signup happens) is locked to the Render backend IPs.

The exact config is **[`Caddyfile`](./Caddyfile)** in this folder — paste it to
`/etc/caddy/Caddyfile` then `sudo systemctl reload caddy`. It relies on the backend ask
endpoint `GET /api/business/crm/tls-check?domain=<host>` (200 = apex or a provisioned
subdomain, else 403).

> Signup lockdown note: Twenty's `signUp` is a GraphQL mutation on `POST /metadata`, not a
> distinct URL, so it can't be matched by route. But **new-workspace creation only happens at
> the apex** `crm.jarvismgco.com` — end users operate entirely on their subdomain. So the
> Caddyfile blocks the apex from everyone except the Render egress ranges
> (`74.220.48.0/24`, `74.220.56.0/24`); subdomains stay public. This keeps
> `IS_SIGN_UP_ENABLED=true` (needed for the backend's service flow) without exposing public
> workspace creation.

## 4. Jarvis backend env (Render)

```
TWENTY_PROVISION_BASE_URL=https://crm.jarvismgco.com   # apex used for signUp/auth calls
TWENTY_SERVICE_EMAIL_DOMAIN=jarvismgco.com             # service signups use crm+<id>@<domain>
# (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY already set — back the workspace + job tables.)
```

Apply the migration `supabase/migrations/batch60_crm_provisioning_jobs.sql` (tracks the
pending/retry/admin-flag state).

## 5. Verify it works (after 1–4)

```bash
# Dry, throwaway: provision a brand-new test user_id end-to-end.
python -m backend.scripts.provision_twenty_workspace --auto --user-id <test-uuid>
# Expect: "Auto-provisioned workspace https://<sub>.crm.jarvismgco.com" + a stored key.

# Then the gate flips:
curl "https://jarvis-backend-4oz6.onrender.com/api/business/crm/workspace?user_id=user_<hex>"
#   -> {"provisioned": true, "embed_url": "https://<sub>.crm.jarvismgco.com", ...}
```

If `--auto` still reports `"New workspace setup is disabled"`, step 1 didn't take effect
(re-check the env + `docker compose up -d`, and that you restarted the **server** container).

---

## Open design item (flag): cockpit iframe login

With service-owned workspaces, the docked **chat** works immediately (it uses the stored API
key). The embedded **iframe** view, though, needs a browser session in that workspace, which
the end user doesn't have. The plan: the backend mints a short-lived login token
(`getAuthTokensFromLoginToken` / `generateTransientToken`) and injects it into the iframe so the
user is auto-signed-in to *their* workspace — the same SSO piece flagged in Phase 3. I'll build
this alongside the reveal once provisioning is verified live.
