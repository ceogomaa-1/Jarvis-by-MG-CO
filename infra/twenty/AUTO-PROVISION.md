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

# Twenty DEFAULTS this to true, which means only server admins may create workspaces.
# Our service signups are NOT admins, so leaving it true fails signUpInNewWorkspace with
# "Workspace creation is restricted to admins". MUST be false (abuse is already blocked by
# the apex lockdown in step 3).
IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=false

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

> ⚠️ Superseded — do NOT IP-lock the apex. In multi-workspace, Twenty uses a SINGLE
> `REACT_APP_SERVER_BASE_URL` (= `SERVER_URL` = the apex) for ALL workspace frontends, exactly
> like Cloud's shared `api.twenty.com`. So every `<sub>.crm.jarvismgco.com` browser calls the
> apex for its API; locking the apex gives users **"Unable to Reach Back-end."** `signUp` rides
> that same shared GraphQL API, so it can't be isolated by host or path. Public workspace
> creation is blocked at the **app layer** instead — see “Blocking public workspace creation”
> below. The Caddyfile no longer locks the apex.

## 4. Jarvis backend env (Render)

```
TWENTY_PROVISION_BASE_URL=https://crm.jarvismgco.com   # apex used for signUp/auth calls
TWENTY_SERVICE_EMAIL_DOMAIN=jarvismgco.com             # service signups use crm+<id>@<domain>
TWENTY_SERVICE_SECRET=<long-random-string-set-once>    # HMAC key for the deterministic
                                                       # service password — NEVER rotate it
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

If `--auto` reports `signUpInNewWorkspace: Workspace creation is restricted to admins`,
then `IS_MULTIWORKSPACE_ENABLED` took effect but the **next** guard is biting:
`IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS` (Twenty's default is **true**). Set it to
`false` on both `server` and `worker`, then `docker compose up -d`:

```bash
# in the same docker-compose.override.yml that carries the other flags
IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=false
# verify it reached the container:
docker compose exec server printenv IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS   # -> false
```

If `--auto` reports `createApiKey: Field "roleId" of required type "UUID!" was not provided`,
you're on a Twenty build whose `createApiKey` requires a role. The flow now handles this:
it calls `getRoles` and attaches the full-settings (Admin) role to the backend key — no
action needed.

> Self-heal / retry: provisioning is now idempotent. The service password is **deterministic**
> (HMAC of the user_id), so a retry that finds the service user `crm+<hex>@jarvismgco.com`
> already created by a prior failed attempt **signs in** and continues instead of colliding.
> Set **`TWENTY_SERVICE_SECRET`** (a long random string) in the Jarvis backend env and never
> change it — it's the HMAC key; rotating it makes previously-created service accounts
> unrecoverable. (Falls back to `APP_SECRET`, then `SUPABASE_SERVICE_ROLE_KEY`, if unset.)
>
> One-time cleanup: service accounts created **before** this deterministic-password change
> have random passwords we never stored, so signIn can't recover them — delete those orphans
> in Twenty (Settings → Members) once, then re-run `--auto`. New signups are unaffected.

---

## Blocking public workspace creation (without breaking the cockpit)

The cockpit failed with **"Unable to Reach Back-end"** because the apex was IP-locked, but the
apex IS the shared API every workspace frontend calls. Fix = stop locking the apex and block
public workspace creation in-app instead. Confirmed from Twenty source: `assertSignUpEnabled`
runs first with **no admin bypass** (so `IS_SIGN_UP_ENABLED` must stay `true`), and only the
**first-ever** user on an instance is auto-granted server admin (`shouldGrantServerAdmin =
!hasServerAdmin()`). So one privileged account creates every workspace.

**Switch to Option 2 — a shared server-admin provisioner.** Each workspace still gets its own
workspace-scoped API key (isolation unchanged); only the *creator* changes.

1. Render env: pick a provisioner identity and a strong password.
   ```
   TWENTY_PROVISIONER_EMAIL=crm-provisioner@jarvismgco.com
   TWENTY_PROVISIONER_PASSWORD=<long-random>      # or omit → derived from TWENTY_SERVICE_SECRET
   ```
2. Create the account (apex still reachable from Render). Run from Render:
   ```bash
   python -m backend.scripts.provision_twenty_workspace --init-provisioner
   ```
3. Promote it to a server admin on the VPS (no public mutation grants this):
   ```bash
   docker compose exec db psql -U "$PG_DATABASE_USER" -d default -c \
     "UPDATE core.\"user\" SET \"canAccessFullAdminPanel\"=true, \"canImpersonate\"=true \
      WHERE email='crm-provisioner@jarvismgco.com';"
   # (table is core.\"user\"; if your build uses public.\"user\", adjust the schema.)
   ```
4. Lock public creation + unlock the shared API, then reload:
   ```bash
   # docker-compose.override.yml (server AND worker):
   IS_WORKSPACE_CREATION_LIMITED_TO_SERVER_ADMINS=true
   docker compose up -d
   # /etc/caddy/Caddyfile: drop the @apex_not_backend block (see this folder's Caddyfile),
   sudo systemctl reload caddy
   ```
5. Verify:
   ```bash
   python -m backend.scripts.provision_twenty_workspace --auto --user-id <fresh-uuid>   # still works (admin creates it)
   curl -s -o /dev/null -w "%{http_code}\n" https://crm.jarvismgco.com/healthz           # 200 from a normal IP now
   # public-creation blocked: a signUp+signUpInNewWorkspace from a non-admin must return
   #   "Workspace creation is restricted to admins"
   ```
   Then open a fresh signup's cockpit — the empty CRM (tables, no red error) should load.

> Sequencing matters: do 1–3 BEFORE step 4. If you flip the flag to `true` before the
> provisioner exists + is promoted, provisioning fails (`provisioner signIn …`). To roll back
> instantly, set the flag `false` again (legacy per-user signups resume).

---

## Open design item (flag): cockpit iframe login

With service-owned workspaces, the docked **chat** works immediately (it uses the stored API
key). The embedded **iframe** view, though, needs a browser session in that workspace, which
the end user doesn't have. The plan: the backend mints a short-lived login token
(`getAuthTokensFromLoginToken` / `generateTransientToken`) and injects it into the iframe so the
user is auto-signed-in to *their* workspace — the same SSO piece flagged in Phase 3. I'll build
this alongside the reveal once provisioning is verified live.
