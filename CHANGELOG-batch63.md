# Batch 63 — Jarvis OS1 tiered paywall (NEW users only; existing grandfathered)

Gates Jarvis OS1 (Business) behind a CAD tiered paywall for **new** users. **Existing users are
grandfathered** — flagged at deploy time, treated as active, and passed straight into OS1 without
ever seeing pricing or being charged. Additive: Personal, CRM, Leads, provisioning, and the
MG&CO / Property Partners RE workspaces are untouched.

## Flow
1. Personal's "Jarvis for Business →" switch (same button/place) now navigates to
   `https://www.jarvismgco.com/os1` (override: `NEXT_PUBLIC_OS1_URL`).
2. `/os1` has Sign up / Login (top-right) — Google OAuth on the **same Supabase** as Personal,
   so existing creds work (one-time login).
3. On auth, the gate reads `GET /api/os1/status`:
   - `has_access` (active_subscription **OR** grandfathered) → enter OS1 (`/business/chat`).
   - else → pricing screen.
4. Pricing (Pro / Emperor / Tailored): Pro & Emperor → Stripe Checkout (7-day trial, card
   required); Tailored / "Want Jarvis tailored…" → `/contact`.

## Tiers (CAD)
- **Pro** $49/mo · $490/yr (2 months free) — chat+voice, capped autonomous sessions, ~5h rolling
  usage, train/feed, 9 bibles, MCP Creation 1.0, Show Me How, basic CRM (no white-label), Buffer 2
  platforms, **no Leads**.
- **Emperor** $199/mo · $1,990/yr — Pro + 5× usage, unlimited Buffer, white-label CRM, Jarvis
  Leads (rule-based + metered overage), customizable UI / moving-blocks + brand.
- **Tailored** — Talk to Sales → Contact page (no checkout).

## Trial anti-abuse
- Card required up front (Checkout trial mode, `payment_method_collection=always`); auto-converts
  at day 7 unless canceled (`trial_settings.end_behavior.missing_payment_method=cancel`).
- **One trial per identity**: blocked by normalized email (gmail dot/plus collapsed) + Stripe card
  fingerprint (recorded in the webhook) + IP. Already-trialed → no trial, straight to pay.
- Disposable/temp-email domains blocked at signup (`os1/email-check`; extend via
  `OS1_EXTRA_DISPOSABLE_DOMAINS`).
- Trial grants a tiny taste only (low message allowance, **no Leads**, no white-label).

## Feature gating (server-side, by tier; grandfathered → Emperor so nothing existing breaks)
- `backend/lib/billing/entitlements.py` is the single source of truth.
- Leads endpoints (`/business/leads/*`) are Emperor-gated + meter billable lookups
  (`os1_leads_usage`) for overage.
- `GET /api/os1/entitlements` exposes flags for UI gating (Buffer cap, white-label, moving-blocks)
  — no-ops for features not built yet.

## Files
- DB: `supabase/migrations/batch63_os1_paywall.sql` (os1_subscriptions + grandfather backfill,
  os1_trial_fingerprints, os1_leads_usage).
- Backend: `backend/lib/billing/{config,store,entitlements,stripe_api,notify,disposable_domains}.py`,
  `backend/routes/os1_billing.py`, wired in `backend/main.py`; Leads gating in
  `backend/routes/business/leads_routes.py`.
- Frontend: `components/ui/{button,card,separator,switch,pricing-cards}.tsx`,
  `components/os1/{OS1Shell,OS1Pricing}.tsx`, `app/os1/page.tsx`, `app/contact/page.tsx`,
  `lib/os1.js`, `components/shared/ModeToggle.js`, `components/os1/OS1CTASection.tsx`.
- Script: `scripts/stripe_setup.py` (creates the 4 CAD prices, prints env).

## Deploy checklist (Mohamed)
1. **Run migration** `batch63_os1_paywall.sql` on Jarvis Supabase (ref `senpmleiuvcgltmspyue`).
   The backfill grandfathers every account that exists at run time — **run only after the code
   is live** so the cutoff is correct.
2. **Stripe**: `$env:STRIPE_SECRET_KEY="sk_..."; python scripts/stripe_setup.py` → paste the 4
   `STRIPE_PRICE_*` env vars into Render.
3. **Render env** (backend): `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `STRIPE_PRICE_PRO_MONTHLY/YEARLY`, `STRIPE_PRICE_EMPEROR_MONTHLY/YEARLY`,
   `OS1_SITE_URL=https://www.jarvismgco.com`, `RESEND_API_KEY` (+ optional `CONTACT_TO`,
   `CONTACT_FROM`).
4. **Stripe webhook** → `https://jarvis-backend-4oz6.onrender.com/api/os1/webhook`; events:
   `checkout.session.completed`, `customer.subscription.created/updated/deleted`,
   `invoice.payment_failed`. Put the signing secret in `STRIPE_WEBHOOK_SECRET`.
5. **Resend**: verify `mgcotechnologies.com` (or set `CONTACT_FROM` to a verified sender). Without
   `RESEND_API_KEY`, contact submissions log (nothing lost) but aren't emailed.

Until Stripe keys are set, `billing_enabled()` is false and checkout returns a graceful error;
the rest of the app is unaffected (same env-gated pattern as Leads/waitlist).
