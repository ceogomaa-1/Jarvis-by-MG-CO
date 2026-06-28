"""
Site Generator for Jarvis OS1 — Batch 1.

Produces a complete, build-clean Next.js 16 (App Router) project from a
user prompt or approved standalone design. Sonnet handles the mechanical
Next.js packaging by default; all structural/config files are hardcoded to
known-good versions so the build never fails on a bad tsconfig or package version.

Returns:
  {
    "project_name": str,          # kebab-case, <=40 chars
    "framework": "nextjs",
    "needs_database": bool,
    "db_plan": {"tables": [...], "migration_sql": "..."} | None,
    "env_keys_needed": ["NEXT_PUBLIC_SUPABASE_URL", ...],
    "files": [{"path": str, "content": str}, ...],
    "summary": str,
    "is_fallback": False,  # retained for wire compatibility; fallbacks are forbidden
  }
"""
import json
import os
import re
from typing import Any

from anthropic import AsyncAnthropic

from backend.lib.business.model_router import SONNET
from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.creation.website_quality import (
    extract_client_name,
    should_use_owner_company,
    validate_site_payload,
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GENERATOR_TIMEOUT = 300.0
_GENERATOR_MAX_TOKENS = 32_000
_SITE_MODEL = os.getenv("JARVIS_SITE_PACKAGING_MODEL", SONNET)
try:
    _GENERATION_ATTEMPTS = max(
        1, min(int(os.getenv("JARVIS_SITE_GENERATION_ATTEMPTS", "1")), 2)
    )
except ValueError:
    _GENERATION_ATTEMPTS = 1


class SiteGenerationError(RuntimeError):
    """Raised when a generated project cannot pass the deploy quality gate."""

# ── DB-needed detection ───────────────────────────────────────────────────────
_DB_KEYWORDS = re.compile(
    r"\b(contact\s+form|sign[- ]?up|sign\s+in|login|auth(?:entication)?|register|"
    r"database|store\s+(?:form\s+)?data|collect\s+(?:emails?|leads?|submissions?)|"
    r"newsletter\s+(?:form|signup)|booking\s+(?:form|system|flow)|"
    r"reservation\s+(?:form|system|flow)|appointment\s+(?:form|system|flow)|"
    r"checkout|payment\s+flow|waitlist\s+form|feedback\s+form)\b",
    re.IGNORECASE,
)


def _needs_db(message: str) -> bool:
    return bool(_DB_KEYWORDS.search(message))


# ── Structural files (hardcoded, build-proven) ───────────────────────────────

def _package_json(name: str, has_db: bool) -> str:
    deps: dict = {
        "next": "16.2.9",
        "react": "19.2.4",
        "react-dom": "19.2.4",
        "motion": "12.42.0",
        "gsap": "3.15.0",
        "clsx": "2.1.1",
        "tailwind-merge": "3.3.1",
        "class-variance-authority": "0.7.1",
        "lucide-react": "1.21.0",
    }
    if has_db:
        deps["@supabase/supabase-js"] = "2.52.1"

    dev: dict = {
        "@types/node": "22.15.30",
        "@types/react": "19.2.17",
        "@types/react-dom": "19.2.3",
        "typescript": "5.9.3",
        "tailwindcss": "3.4.17",
        "postcss": "8.5.6",
        "autoprefixer": "10.4.21",
    }

    return json.dumps({
        "name": name,
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
        },
        "dependencies": deps,
        "devDependencies": dev,
    }, indent=2)


_TSCONFIG = json.dumps({
    "compilerOptions": {
        "target": "ES2017",
        "lib": ["dom", "dom.iterable", "esnext"],
        "allowJs": True,
        "skipLibCheck": True,
        "strict": True,
        "noEmit": True,
        "esModuleInterop": True,
        "module": "esnext",
        "moduleResolution": "bundler",
        "resolveJsonModule": True,
        "isolatedModules": True,
        "jsx": "preserve",
        "incremental": True,
        "plugins": [{"name": "next"}],
        "paths": {"@/*": ["./*"]},
    },
    "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
    "exclude": ["node_modules"],
}, indent=2)

_TAILWIND_CONFIG = '''\
import type { Config } from "tailwindcss"

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--bg)",
        surface: "var(--surface)",
        accent: "var(--accent)",
        "text-primary": "var(--text-primary)",
        "text-muted": "var(--text-muted)",
      },
    },
  },
  plugins: [],
}

export default config
'''

_POSTCSS = '''\
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
'''

_NEXT_CONFIG = '''\
/** @type {import('next').NextConfig} */
const nextConfig = {
  images: { unoptimized: true },
}

module.exports = nextConfig
'''

_UTILS_TS = '''\
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
'''

_GITIGNORE = '''\
/node_modules
/.next/
/out/
/build
.DS_Store
*.pem
npm-debug.log*
.env*.local
.env
.vercel
*.tsbuildinfo
next-env.d.ts
'''

_SUPABASE_CLIENT = '''\
import { createClient } from "@supabase/supabase-js"

let client: ReturnType<typeof createClient> | null = null

export function getSupabase() {
  if (client) return client
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  if (!url || !anonKey) {
    throw new Error("Supabase environment variables are not configured")
  }
  client = createClient(url, anonKey)
  return client
}
'''

_ENV_EXAMPLE = '''\
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
'''


# ── Claude tool contract ──────────────────────────────────────────────────────

_SITE_TOOL: dict = {
    "name": "create_site",
    "description": (
        "Output the complete creative source files for a Next.js 16 landing page / website. "
        "Every field must contain the FULL file content — no truncation, no TODOs, no placeholders."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "kebab-case name derived from the concept, max 40 chars, lowercase + hyphens only",
            },
            "needs_database": {
                "type": "boolean",
                "description": "True if the site has any forms, auth, data storage, or lead capture",
            },
            "summary": {
                "type": "string",
                "description": "Plain-language description of the site (sections, design, features) — 2-4 sentences",
            },
            "db_migration_sql": {
                "type": "string",
                "description": (
                    "PostgreSQL CREATE TABLE + RLS migration SQL (only when needs_database is true). "
                    "Include row-level security ENABLE and a policy that allows anonymous inserts."
                ),
            },
            "layout_tsx": {
                "type": "string",
                "description": "Complete content of app/layout.tsx — sets metadata title/description, imports globals.css, wraps in html/body",
            },
            "globals_css": {
                "type": "string",
                "description": (
                    "Complete content of app/globals.css. Must start with @tailwind base/components/utilities "
                    "and define CSS custom properties: --bg, --surface, --accent, --text-primary, --text-muted, --border"
                ),
            },
            "page_tsx": {
                "type": "string",
                "description": (
                    "Complete content of app/page.tsx — an award-calibre marketing page. Rules:\n"
                    "- First line MUST be: 'use client'\n"
                    "- Imports: react hooks, motion/react (motion, useInView, AnimatePresence, useScroll, useTransform), and lucide-react icons. May import gsap + 'gsap/ScrollTrigger' for complex scroll sequences (register inside useEffect).\n"
                    "- If needs_database: also import ContactForm from '@/components/contact-form'\n"
                    "- DO NOT import from any other local file. Compose shadcn-style accessible primitives and recreate Aceternity/Magic-UI patterns inline (spotlight, tilt/3D card, shimmer button, bento, marquee, animated gradient, FAQ accordion).\n"
                    "- Self-contained: define all sections inline (no separate component files)\n"
                    "- Content flow: clear nav/CTA, cinematic specific hero, proof/useful facts, real offerings/services, differentiated story/experience, conversion path, FAQ when useful, closing CTA, footer\n"
                    "- Animations: motion/react scroll-reveal + stagger where useful; hover/tap micro-interactions; gate non-essential motion behind a prefers-reduced-motion check\n"
                    "- Styling: Tailwind + CSS variables (var(--accent), var(--bg), etc.); fluid type via clamp(); generous intentional spacing; layered depth when conceptually appropriate\n"
                    "- Mobile-first responsive (sm:/md:/lg:); tap targets >=44px; real specific copy, never lorem ipsum\n"
                    "- Art direction must be unique to the target business; never default every industry to dark SaaS"
                ),
            },
            "contact_form_tsx": {
                "type": "string",
                "description": (
                    "Complete content of components/contact-form.tsx — only when needs_database is true. "
                    "A React client component ('use client') that calls getSupabase() from @/lib/supabase lazily on submit. "
                    "Must handle submit, show loading state, and display success/error messages. "
                    "Style with Tailwind + CSS variables."
                ),
            },
            "readme_md": {
                "type": "string",
                "description": "README.md content — project title, brief description, local dev instructions",
            },
        },
        "required": [
            "project_name",
            "needs_database",
            "summary",
            "layout_tsx",
            "globals_css",
            "page_tsx",
            "readme_md",
        ],
    },
}

_SYSTEM_PROMPT = """\
You are a world-class product designer and senior front-end engineer. You build distinctive,
conversion-aware marketing sites with the craft of a top digital studio. The bar is "astonishing
and specific", not merely "valid React".

IDENTITY AND ARTIFACT BOUNDARY (NON-NEGOTIABLE):
- Build for the target business in the PRIMARY BUILD BRIEF, never for the account owner, MG&CO,
  Jarvis, or the chat application.
- Never reproduce the instruction, conversation, chat bubbles, preview controls, or builder UI.
- Never include Jarvis/MG&CO attribution in client-facing content.
- Preserve facts from supplied current-site research, but do not invent awards, ratings, client
  logos, metrics, testimonials, prices, addresses, hours, or claims.

DESIGN SYSTEM:
- Start with a one-sentence art direction derived from the actual business and express it in the
  code. Hospitality should feel sensory and human; health/professional services calm and credible;
  technology/creative sharper and more kinetic; local trades direct, grounded, and proof-led.
- Define semantic tokens: --bg, --surface, --surface-2, --accent, --accent-2, --text-primary,
  --text-muted, --border, --focus. Use one dominant accent plus tonal variants.
- Use next/font/google in layout.tsx for a characterful display face and a legible body face.
  Use a fluid modular scale via clamp(), coherent spacing, and a deliberate radius language.
- Compose accessible patterns in the spirit of shadcn/ui. Recreate selective Aceternity/Magic UI
  patterns inline only when they reinforce the concept. Avoid identical cards everywhere.
- Motion for React handles entrances, gestures, layout, and scroll-linked details. GSAP
  ScrollTrigger is reserved for complex timelines. Always honor prefers-reduced-motion.
- No AI-template fingerprints: no generic "Built to..." hero, no Fast/Modern/Yours cards, no fake
  logo strip, no neon-on-black for every industry, no rainbow gradients, no decorative dashboard
  unrelated to the client, no lorem ipsum, placeholders, TODOs, or truncated sections.

CONTENT FLOW:
Clear nav and CTA → cinematic specific hero → verified proof/useful facts → real offerings/menu/
services → differentiated story or experience → frictionless conversion path → FAQ when useful →
strong closing CTA → complete footer. Use at least five substantive sections and sharp real copy.

Tech stack (exact versions, already in package.json — do NOT add others):
  - Next.js 16.2.9, React 19.2.4, TypeScript 5.9.3
  - Tailwind CSS 3.4.17
  - Motion 12.42.0 via motion/react
  - GSAP 3.15.0 (+ ScrollTrigger, registered client-side) for complex scroll sequences
  - lucide-react 1.21.0
  - @supabase/supabase-js 2.52.1 (only if needs_database)
  - clsx 2.1.1 + tailwind-merge 3.3.1 (via @/lib/utils cn())

CRITICAL BUILD RULES (these keep the deploy green — never violate):
1. page.tsx MUST start with "use client" (Motion/GSAP require it).
2. ONLY import from: react, motion/react, gsap, gsap/ScrollTrigger, lucide-react, @/lib/utils,
   and (if needs_database) @/components/contact-form and @/lib/supabase.
   DO NOT import shadcn/ui or Aceternity packages — recreate selected patterns inline.
3. All TypeScript must be valid. No implicit any. No missing props. Guard GSAP/DOM access with useEffect + refs (never at module top-level).
4. globals.css MUST have @tailwind base, @tailwind components, @tailwind utilities, then your token :root vars and any keyframes.
5. layout.tsx uses `export const metadata` (server component, NO "use client").
6. Every string in JSX with quotes uses &quot; or template literals — no raw " in attributes.
7. Return COMPLETE file content. No "// ... rest of component". No truncation.
8. If needs_database is true, contact-form.tsx must call getSupabase() lazily inside submit handling.
"""


# ── Main generator function ───────────────────────────────────────────────────

async def generate_site(user_message: str, context: dict) -> dict:
    """
    Generate and validate a complete Next.js site from a user prompt.
    Returns the site dict with files[], project_name, needs_database, etc.
    """
    context = dict(context or {})
    has_db = _needs_db(user_message)
    client_name = context.get("client_name") or extract_client_name(user_message)
    if client_name:
        context["client_name"] = client_name
    user_prompt = _build_site_prompt(user_message, context, has_db)

    if not ANTHROPIC_API_KEY:
        raise SiteGenerationError(
            "Site generation is unavailable because the Anthropic API key is not configured."
        )

    tool_result: dict[str, Any] = {}
    repair_notes: list[str] = []
    last_problem = "the model returned no usable project"
    for attempt in range(_GENERATION_ATTEMPTS):
        prompt = user_prompt
        if repair_notes:
            prompt += (
                "\n\nQUALITY-GATE RETRY: The previous project was rejected for these reasons:\n- "
                + "\n- ".join(repair_notes)
                + "\nRegenerate every creative file from scratch and fix all issues."
            )
        try:
            tool_result = await _call_site_model(prompt)
        except Exception as exc:
            last_problem = f"{type(exc).__name__}: {str(exc) or 'stream interrupted'}"
            print(
                f"site_generator: streamed model attempt {attempt + 1} failed: "
                f"{last_problem}"
            )
            repair_notes = ["the model stream did not finish; return complete, concise files"]
            continue

        # The DB decision is deterministic. Do not let a stray mention of "CRM"
        # or an over-eager model silently add a database to a static marketing site.
        tool_result["needs_database"] = has_db
        repair_notes = validate_site_payload(tool_result, user_message, context)
        if repair_notes:
            last_problem = "; ".join(repair_notes[:6])
            print(
                f"site_generator: quality gate rejected attempt {attempt + 1}: "
                f"{last_problem}"
            )
            continue
        break
    else:
        raise SiteGenerationError(
            "I could not produce a deploy-safe project that passed the quality checks. "
            f"Nothing was pushed to GitHub or Vercel. Last issue: {last_problem}"
        )

    project_name = _sanitize_name(tool_result.get("project_name", "jarvis-site"))
    needs_database = has_db
    summary = tool_result.get("summary", "")
    layout_tsx = tool_result.get("layout_tsx", "")
    globals_css = tool_result.get("globals_css", "")
    page_tsx = tool_result.get("page_tsx", "")
    contact_form_tsx = tool_result.get("contact_form_tsx", "")
    readme_md = tool_result.get("readme_md", f"# {project_name}\n\nProduction website.\n")
    db_sql = tool_result.get("db_migration_sql", "")

    # Assemble files: hardcoded structural + Claude-generated creative
    files: list[dict] = [
        {"path": "package.json", "content": _package_json(project_name, needs_database)},
        {"path": "tsconfig.json", "content": _TSCONFIG},
        {"path": "tailwind.config.ts", "content": _TAILWIND_CONFIG},
        {"path": "postcss.config.js", "content": _POSTCSS},
        {"path": "next.config.js", "content": _NEXT_CONFIG},
        {"path": ".gitignore", "content": _GITIGNORE},
        {"path": "lib/utils.ts", "content": _UTILS_TS},
        {"path": "app/layout.tsx", "content": layout_tsx or _default_layout(project_name)},
        {"path": "app/globals.css", "content": globals_css or _default_globals()},
        {"path": "app/page.tsx", "content": page_tsx},
        {"path": "README.md", "content": readme_md},
    ]

    if needs_database:
        files.append({"path": "lib/supabase.ts", "content": _SUPABASE_CLIENT})
        if contact_form_tsx:
            files.append({"path": "components/contact-form.tsx", "content": contact_form_tsx})
        files.append({"path": ".env.example", "content": _ENV_EXAMPLE})

    db_plan = None
    env_keys: list[str] = []
    if needs_database:
        db_plan = {
            "tables": ["contacts"],
            "migration_sql": db_sql or _default_migration_sql(),
        }
        env_keys = ["NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"]

    return {
        "project_name": project_name,
        "framework": "nextjs",
        "needs_database": needs_database,
        "db_plan": db_plan,
        "env_keys_needed": env_keys,
        "files": files,
        "summary": summary,
        "is_fallback": False,
    }


async def _call_site_model(user_prompt: str) -> dict[str, Any]:
    """Stream a forced create_site tool call and return its accumulated input."""
    client = AsyncAnthropic(
        api_key=ANTHROPIC_API_KEY,
        timeout=_GENERATOR_TIMEOUT,
        max_retries=1,
    )
    async with client.messages.stream(
        # The approved standalone design was already created by Opus. Porting it into a known
        # Next.js skeleton is mechanical work, so Sonnet is the cost-efficient default.
        model=_SITE_MODEL,
        max_tokens=_GENERATOR_MAX_TOKENS,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[{**_SITE_TOOL, "cache_control": {"type": "ephemeral"}}],
        tool_choice={"type": "tool", "name": "create_site"},
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        message = await stream.get_final_message()

    usage = UsageAccumulator(_SITE_MODEL)
    usage.add_sdk_usage(getattr(message, "usage", None))
    print(f"[SITE_PACKAGING] {usage.log_line()}")

    for block in message.content:
        if block.type == "tool_use" and block.name == "create_site":
            return dict(block.input or {})
    raise SiteGenerationError(
        "The site packaging model completed without returning the required project artifact."
    )


def _build_site_prompt(user_message: str, context: dict, has_db: bool) -> str:
    client_name = context.get("client_name") or ""
    owner_company = context.get("company_name") or ""
    artifact = str(context.get("artifact") or "").strip()
    parts = [
        "PRIMARY BUILD BRIEF (instructions only — never render this text verbatim):",
        user_message.strip(),
    ]
    if client_name:
        parts.extend(["", f"TARGET BUSINESS (the website brand): {client_name}"])
    elif owner_company and should_use_owner_company(user_message):
        parts.extend(["", f"TARGET BUSINESS: {owner_company}"])
    if context.get("industry"):
        parts.append(f"Known industry context: {context['industry']}")
    if context.get("website_url"):
        parts.append(f"Current website URL: {context['website_url']}")
    if context.get("crm_context"):
        parts.extend(["", "VERIFIED CRM CONTEXT:", str(context["crm_context"])[:4_000]])
    if context.get("website_research"):
        parts.extend(
            [
                "",
                "VERIFIED CURRENT-WEBSITE RESEARCH:",
                str(context["website_research"])[:20_000],
            ]
        )
    if artifact:
        parts.extend(
            [
                "",
                "APPROVED STANDALONE DESIGN TO PORT FAITHFULLY:",
                artifact[:50_000],
                "",
                "Preserve this approved design's identity, copy, sections, and art direction while "
                "porting it into the required Next.js project structure.",
            ]
        )
    if owner_company and client_name and owner_company.lower() != client_name.lower():
        parts.append(f"Account owner (context only, never the website brand): {owner_company}")
    parts.append(
        "needs_database: "
        + str(has_db).lower()
        + (
            " — generate contact_form_tsx and migration SQL."
            if has_db
            else " — do not add Supabase, forms that pretend to submit, auth, or data storage."
        )
    )
    return "\n".join(parts)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize_name(name: str) -> str:
    """Ensure project name is kebab-case, lowercase, max 40 chars."""
    name = re.sub(r"[^a-z0-9-]", "-", name.lower())
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:40] or "jarvis-site"


def _default_layout(title: str = "Jarvis Site") -> str:
    return f'''\
import type {{ Metadata }} from "next"
import "./globals.css"

export const metadata: Metadata = {{
  title: "{title.replace("-", " ").title()}",
  description: "Official website",
}}

export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode
}}) {{
  return (
    <html lang="en">
      <body>{{children}}</body>
    </html>
  )
}}
'''


def _default_globals() -> str:
    return """\
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --bg: #0a0a0a;
  --surface: #141414;
  --accent: #c84b31;
  --text-primary: #f3ead9;
  --text-muted: rgba(243,234,217,0.55);
  --border: rgba(243,234,217,0.08);
}

* { box-sizing: border-box; }

body {
  background: var(--bg);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  -webkit-font-smoothing: antialiased;
}
"""


def _default_migration_sql() -> str:
    return """\
-- Contact form submissions
CREATE TABLE IF NOT EXISTS contacts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  email       text NOT NULL,
  message     text,
  created_at  timestamptz DEFAULT now()
);

ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_anon_insert" ON contacts
  FOR INSERT TO anon WITH CHECK (true);
"""


def _fallback_site(user_message: str, context: dict, has_db: bool = False) -> dict:
    """Compatibility tombstone: generic sites must never be shipped as successful work."""
    raise SiteGenerationError(
        "Generic fallback sites are disabled. The requested project was not generated."
    )

    # Kept temporarily below for old imports during the migration window. This
    # branch is intentionally unreachable and can never enter preview/deploy.
    company = context.get("company_name") or "Your Brand"
    industry = context.get("industry") or "business"
    project_name = _sanitize_name(f"{company}-{industry}-site")
    title = company.replace('"', "")
    request = user_message.replace("`", "'")

    page_tsx = f'''\
"use client"

import {{ motion }} from "framer-motion"
import {{ ArrowRight, CheckCircle2, Sparkles }} from "lucide-react"

const bullets = [
  "Premium conversion-focused landing page",
  "Mobile responsive sections and strong CTA flow",
  "Built on a production-ready Next.js stack",
]

export default function Home() {{
  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--text-primary)]">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="text-sm font-semibold uppercase tracking-[0.28em]">{title}</div>
        <a href="#contact" className="rounded-full border border-[var(--border)] px-4 py-2 text-sm text-[var(--text-muted)]">
          Start now
        </a>
      </nav>

      <section className="mx-auto grid max-w-6xl gap-12 px-6 py-20 md:grid-cols-[1.1fr_0.9fr] md:items-center">
        <motion.div initial={{{{ opacity: 0, y: 18 }}}} animate={{{{ opacity: 1, y: 0 }}}} transition={{{{ duration: 0.7 }}}}>
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm text-[var(--text-muted)]">
            <Sparkles className="h-4 w-4 text-[var(--accent)]" />
            Built from your request
          </div>
          <h1 className="max-w-3xl text-5xl font-semibold leading-tight md:text-7xl">
            A sharper web presence for {title}.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-[var(--text-muted)]">
            {request}
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <a href="#contact" className="inline-flex items-center gap-2 rounded-full bg-[var(--accent)] px-6 py-3 font-semibold text-black">
              Launch the project <ArrowRight className="h-4 w-4" />
            </a>
            <a href="#strategy" className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] px-6 py-3 text-[var(--text-primary)]">
              View strategy
            </a>
          </div>
        </motion.div>

        <motion.div initial={{{{ opacity: 0, scale: 0.96 }}}} animate={{{{ opacity: 1, scale: 1 }}}} transition={{{{ duration: 0.7, delay: 0.1 }}}}
          className="rounded-3xl border border-[var(--border)] bg-[linear-gradient(145deg,rgba(200,75,49,0.18),rgba(243,234,217,0.04))] p-8 shadow-2xl">
          <div className="mb-10 h-48 rounded-2xl bg-[radial-gradient(circle_at_30%_20%,rgba(200,75,49,0.75),transparent_35%),linear-gradient(135deg,#181818,#050505)]" />
          <div className="space-y-4">
            {{bullets.map((item) => (
              <div key={{item}} className="flex items-start gap-3 text-sm text-[var(--text-muted)]">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" />
                <span>{{item}}</span>
              </div>
            ))}}
          </div>
        </motion.div>
      </section>

      <section id="strategy" className="border-y border-[var(--border)] bg-[var(--surface)]/50">
        <div className="mx-auto grid max-w-6xl gap-6 px-6 py-16 md:grid-cols-3">
          {{["Positioning", "Offer", "Conversion"].map((label, index) => (
            <div key={{label}} className="rounded-2xl border border-[var(--border)] bg-black/20 p-6">
              <div className="mb-4 text-sm text-[var(--accent)]">0{{index + 1}}</div>
              <h2 className="text-2xl font-semibold">{{label}}</h2>
              <p className="mt-3 text-sm leading-6 text-[var(--text-muted)]">
                Clear, premium messaging shaped to help visitors understand the value quickly and take action.
              </p>
            </div>
          ))}}
        </div>
      </section>

      <section id="contact" className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h2 className="text-4xl font-semibold">Ready to turn attention into action?</h2>
        <p className="mx-auto mt-4 max-w-2xl text-[var(--text-muted)]">
          This version is the reliable deploy fallback. Jarvis can refine copy, sections, and visuals from here.
        </p>
      </section>
    </main>
  )
}}
'''

    files = [
        {"path": "package.json", "content": _package_json(project_name, False)},
        {"path": "tsconfig.json", "content": _TSCONFIG},
        {"path": "tailwind.config.ts", "content": _TAILWIND_CONFIG},
        {"path": "postcss.config.js", "content": _POSTCSS},
        {"path": "next.config.js", "content": _NEXT_CONFIG},
        {"path": ".gitignore", "content": _GITIGNORE},
        {"path": "lib/utils.ts", "content": _UTILS_TS},
        {"path": "app/layout.tsx", "content": _default_layout(project_name)},
        {"path": "app/globals.css", "content": _default_globals()},
        {"path": "app/page.tsx", "content": page_tsx},
        {"path": "README.md", "content": f"# {project_name}\n\nProduction website.\n"},
    ]
    return {
        "project_name": project_name,
        "framework": "nextjs",
        "needs_database": False,
        "db_plan": None,
        "env_keys_needed": [],
        "files": files,
        "summary": "Fallback build-clean Next.js site generated after the creative generator failed or timed out.",
        "is_fallback": True,
    }
