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

## 3. Wildcard TLS (Caddy)

Wildcard certs require the **DNS-01** challenge, so Caddy needs your DNS provider's plugin +
an API token. Example for Cloudflare (`caddy-dns/cloudflare` build):

```caddyfile
*.crm.jarvismgco.com, crm.jarvismgco.com {
    reverse_proxy localhost:3000
    tls {
        dns cloudflare {env.CF_API_TOKEN}
    }
    # Allow the Jarvis app to embed the cockpit (Phase 3).
    header Content-Security-Policy "frame-ancestors 'self' https://jarvismgco.com https://*.jarvismgco.com"
    header -X-Frame-Options
}
```

Set `CF_API_TOKEN` in Caddy's environment (a token scoped to that zone's DNS edit). Other
providers: swap the `dns` directive (route53, digitalocean, etc.) and rebuild Caddy with that
plugin.

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
