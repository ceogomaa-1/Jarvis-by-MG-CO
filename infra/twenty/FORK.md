# Rue CRM — fork & rebase workflow

Rue CRM is a **white-labeled fork of [Twenty](https://twenty.com)** (AGPL-3.0).
We run our own build so the product reads as *Rue CRM*, not Twenty. The hard rule
that keeps us sane: **all branding lives in one overlay folder** (`jarvis-branding/`) so
upstream releases rebase cleanly and we never diverge into a maintenance trap.

> AGPL obligations are real — read [`AGPL-COMPLIANCE.md`](./AGPL-COMPLIANCE.md) before
> deploying. The short version: because users interact with this over a network, we must
> offer them the corresponding source (our fork included).

---

## 1. Create the fork (one-time — Mohamed)

```bash
# In our GitHub org (e.g. MG-CO):
#   1. Fork twentyhq/twenty  →  MG-CO/jarvis-crm   (or import; keep history)
#   2. Clone it locally:
git clone git@github.com:MG-CO/jarvis-crm.git
cd jarvis-crm

# Pin to the EXACT release we deployed in Phase 1 (docker image v0.42.0):
git checkout -b jarvis v0.42.0          # our long-lived branch starts at the pinned tag

# Track upstream so we can pull future releases:
git remote add upstream https://github.com/twentyhq/twenty.git
git fetch upstream --tags
```

Our work lives on the **`jarvis`** branch. `main` mirrors upstream (don't commit branding there).

## 2. Apply branding as an overlay (clean rebase strategy)

Branding does **not** get scattered across core components. It lives in **one folder**,
`jarvis-branding/`, plus a single apply script. See
[`branding/README.md`](./branding/README.md) for exactly which files map to which brand
element. The build copies the overlay into the source tree right before `docker build`:

```bash
# from the fork root, on the jarvis branch:
./jarvis-branding/apply.sh          # copies overlay assets/strings/theme into src
docker build -f infra/twenty/branding/Dockerfile.jarvis -t ghcr.io/MG-CO/jarvis-crm:v0.42.0 .
docker push ghcr.io/MG-CO/jarvis-crm:v0.42.0
```

Because every edit is in `jarvis-branding/` (and a handful of pointer edits the apply
script makes), a rebase conflict surface is tiny.

## 3. Rebase onto a new Twenty release

```bash
git fetch upstream --tags
git checkout jarvis
git rebase v0.43.0                  # the new upstream tag

# Resolve conflicts (should be small — branding is isolated). Then:
./jarvis-branding/apply.sh          # re-apply overlay onto the new tree
# Smoke-test locally (docker compose up with the freshly built image), then:
docker build -f infra/twenty/branding/Dockerfile.jarvis -t ghcr.io/MG-CO/jarvis-crm:v0.43.0 .
```

**Always back up the production DB before deploying a rebased image** (see
[`README.md`](./README.md) §5 — `pg_dump`). Bump the image tag in
[`docker-compose.yml`](./docker-compose.yml) deliberately; never track `:latest`.

## 4. Upgrade checklist

1. `pg_dump` backup taken and copied offsite.
2. Rebased onto the new tag; conflicts resolved; `apply.sh` re-run.
3. Branded image built + pushed with the new version tag.
4. `docker-compose.yml` image tag bumped (server **and** worker).
5. `docker compose pull && docker compose up -d` — `server` runs DB migrations.
6. Verify: no "Twenty" strings, dark luxury theme default, login + emails branded,
   per-client workspaces still resolve (run `provision_twenty_workspace.py --list`).

---

## Why a fork (not just env vars)

Twenty's app name, logo, favicon and login screen are compiled into the frontend bundle —
they are **not** fully env-configurable in v0.42. A thin fork with an isolated overlay is
the only way to fully remove "Twenty" branding while keeping a clean upgrade path. The
overlay approach is what keeps the fork cheap to maintain.
