# Rue CRM — AGPL-3.0 compliance

Rue CRM is a fork of [Twenty](https://github.com/twentyhq/twenty), licensed under the
**GNU Affero General Public License v3.0 (AGPL-3.0)**. White-labeling and self-hosting are
permitted. The obligation we must actively satisfy:

> **AGPL §13 (network use):** if users interact with the software remotely over a network,
> they must be offered access to the **Corresponding Source** — *including our modifications*
> — under the same license.

Running Rue CRM as a hosted CRM that clients log into = "interact over a network." So we
must publish our source. Below is how we satisfy it. **None of this is optional.**

---

## What we must provide

1. **Corresponding source of our fork**, including the `jarvis-branding/` overlay and any
   code changes, kept current with the deployed version.
2. **A visible offer** in the running app pointing users to that source.
3. **The license text** (AGPL-3.0) retained in the source.

## How we satisfy it

### 1. Public source repository
The fork `MG-CO/jarvis-crm` is the corresponding source. The deployed image tag maps 1:1 to
a git tag in that repo (e.g. image `v0.42.0` ⇄ branch `jarvis` at tag `jarvis-v0.42.0`).

> **Decision for Mohamed:** the fork repo must be **publicly readable** (or source offered
> on request to every user). A private fork that hosted users can't reach does **not** satisfy
> AGPL. Recommended: keep `MG-CO/jarvis-crm` public. Branding art can stay ours (trademark);
> the *code* must be available. ⚠️ Flag — confirm the repo is public before go-live.

### 2. In-app source offer
A footer/settings link **"Source code (AGPL)"** → `https://github.com/MG-CO/jarvis-crm`.
- Add it in the branding overlay (don't remove Twenty's source link without replacing it).
- The `Dockerfile.jarvis` also stamps `org.opencontainers.image.source` on the image.

The `links.map` step removes Twenty's *marketing* links but we **keep a source link** — see
the overlay note. Removing the source link entirely would breach AGPL.

### 3. License retention
- Keep the upstream `LICENSE` (AGPL-3.0) in the fork — do not delete or relicense.
- Our modifications inherit AGPL-3.0. We may trademark "Rue CRM" and our logos, but the
  code stays AGPL.

## What is NOT restricted
- Charging clients to use the hosted CRM (AGPL allows commercial hosting).
- White-labeling the UI / removing Twenty's name and branding from the *interface*.
- Keeping client *data* private (AGPL covers source code, never user data).

## Trademark note
"Twenty" is the upstream project's name/mark; removing it from our UI is expected and fine.
"Rue CRM" / "MG&CO" marks and logo art are ours and not covered by AGPL.

---

### Go-live checklist (AGPL)
- [ ] `MG-CO/jarvis-crm` is public (or a written source offer is in place). **Mohamed to confirm.**
- [ ] Deployed image tag ⇄ a pushed git tag in the fork.
- [ ] In-app footer/settings "Source code (AGPL)" link present and correct.
- [ ] Upstream `LICENSE` retained in the fork.
