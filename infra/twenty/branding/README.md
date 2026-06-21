# Jarvis CRM — branding overlay

Everything that turns Twenty into **Jarvis CRM** lives here, in ONE folder, so upstream
rebases stay clean (see [`../FORK.md`](../FORK.md)). Nothing branding-related should be
edited directly in core components — if you find yourself doing that, add the asset here
and point the apply script at it instead.

Product name: **Jarvis CRM** · Design language: **MG&CO — dark, minimal, luxury**
(Notion/Spotify-inspired). Dark theme is the default.

---

## What this overlay changes

| Brand element | Upstream location (verify against the pinned tag) | Overlay source |
|---|---|---|
| App / product name ("Twenty" → "Jarvis CRM") | strings in `packages/twenty-front/src` and `packages/twenty-emails` | `strings.map` (apply.sh sed-replaces) |
| Browser tab title | `packages/twenty-front/index.html` `<title>` | `index.title.html` |
| Favicon | `packages/twenty-front/public/favicon*.png/.ico` | `favicon/` |
| Logo (app + login) | `packages/twenty-front/src/...` logo SVG/components + `public/images/logos` | `logo/` |
| Loading / splash screen | front loading component | `logo/` (same mark) |
| Login page wordmark/copy | front sign-in module | `strings.map` + `logo/` |
| Default theme (dark, accent, type) | `packages/twenty-front/src/modules/ui/theme` | `jarvis-theme.ts` |
| Default color scheme = Dark | workspace default in front theme provider | set by `apply.sh` |
| Transactional emails (invite, reset, notify) | `packages/twenty-emails/src` | `strings.map` + email env |
| External Twenty links (docs/support/marketing) | footer/menu link constants | `links.map` (replace/remove) |

> **Why "verify against the pinned tag":** Twenty's source tree moves between releases.
> The table is correct as of **v0.42.0**. `apply.sh` discovers files by content
> (grep for the string/asset) rather than hard-coded paths wherever possible, so small
> upstream moves don't silently no-op. After any rebase, run the VERIFY checklist below.

## Files in this overlay

- `jarvis-theme.ts` — MG&CO design tokens (palette, accent, radius, typography) mapped to
  Twenty's theme shape. This is the single source of truth for the look.
- `env.branding.example` — env vars consumed by `docker-compose.yml` (app name, support
  URL, email sender) for the bits that *are* env-driven.
- `Dockerfile.jarvis` — builds the branded image from the fork (runs `apply.sh` first).
- `strings.map`, `links.map` — `old<TAB>new` replacement tables `apply.sh` applies.
- `logo/`, `favicon/` — drop the Jarvis CRM marks here (PNG/SVG/ICO). **Placeholders until
  Mohamed supplies final art** — see "Assets needed" below.
- `apply.sh` — the only thing that touches the source tree. Idempotent; safe to re-run.

`apply.sh`, `strings.map`, `links.map`, `logo/`, `favicon/` live in the **fork** under
`jarvis-branding/` (this folder documents them and holds the canonical theme + Dockerfile
that the repo tracks). Keeping the doc + theme + Dockerfile here means Jarvis-side review
of the brand without cloning the fork.

## Assets needed from Mohamed (flagged)

- [ ] Final **Jarvis CRM logo** (light-on-dark): full wordmark SVG + square app mark SVG.
- [ ] **Favicon** set (32px, 180px apple-touch, .ico).
- [ ] Confirm accent color (`jarvis-theme.ts` ships a default MG&CO gold/amber on near-black;
      change one token to restyle).
- [ ] Confirm support/contact URL to replace Twenty's (defaults to `https://jarvismgco.com`).

## VERIFY (after every build / rebase)

1. `grep -ri "twenty" packages/twenty-front/build packages/twenty-emails/dist` returns
   nothing user-visible (ignore license headers / package internals).
2. Tab title = "Jarvis CRM"; favicon is ours.
3. Login page + loading screen show the Jarvis mark, no Twenty logo.
4. Color scheme defaults to Dark with the MG&CO accent.
5. Send a test invite → email reads "Jarvis CRM", from our domain.
6. Footer/menu external links point to ours (or are removed) — no links to twenty.com.
