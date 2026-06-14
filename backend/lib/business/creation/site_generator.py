"""
Site Generator for Jarvis OS1 — Batch 1.

Produces a complete, build-clean Next.js 14 (App Router) project from a
user prompt.  Claude Opus generates the creative page/component code;
all structural/config files are hardcoded to known-good versions so the
build never fails on a bad tsconfig or package version.

Returns:
  {
    "project_name": str,          # kebab-case, <=40 chars
    "framework": "nextjs",
    "needs_database": bool,
    "db_plan": {"tables": [...], "migration_sql": "..."} | None,
    "env_keys_needed": ["NEXT_PUBLIC_SUPABASE_URL", ...],
    "files": [{"path": str, "content": str}, ...],
    "summary": str,
    "is_fallback": bool,  # True if the creative generator failed/timed out and
                          # this is the generic emergency template instead
  }
"""
import json
import os
import re
from typing import Any

import httpx

from backend.lib.business.model_router import OPUS

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GENERATOR_TIMEOUT = 45.0

# ── DB-needed detection ───────────────────────────────────────────────────────
_DB_KEYWORDS = re.compile(
    r"\b(contact\s+form|sign[- ]?up|sign\s+in|login|auth|register|submit|"
    r"database|store\s+data|collect|leads?|crm|newsletter|booking|reservation|"
    r"appointment|order|checkout|payment|waitlist|feedback\s+form)\b",
    re.IGNORECASE,
)


def _needs_db(message: str) -> bool:
    return bool(_DB_KEYWORDS.search(message))


# ── Structural files (hardcoded, build-proven) ───────────────────────────────

def _package_json(name: str, has_db: bool) -> str:
    deps: dict = {
        "next": "14.2.5",
        "react": "18.3.1",
        "react-dom": "18.3.1",
        "framer-motion": "11.3.28",
        "clsx": "2.1.1",
        "tailwind-merge": "2.5.2",
        "class-variance-authority": "0.7.0",
        "lucide-react": "0.417.0",
    }
    if has_db:
        deps["@supabase/supabase-js"] = "2.45.4"

    dev: dict = {
        "@types/node": "20.14.10",
        "@types/react": "18.3.3",
        "@types/react-dom": "18.3.0",
        "typescript": "5.5.3",
        "tailwindcss": "3.4.6",
        "postcss": "8.4.40",
        "autoprefixer": "10.4.20",
        "eslint": "8.57.0",
        "eslint-config-next": "14.2.5",
    }

    return json.dumps({
        "name": name,
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "dev": "next dev",
            "build": "next build",
            "start": "next start",
            "lint": "next lint",
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

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
'''

_ENV_EXAMPLE = '''\
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
'''


# ── Claude tool contract ──────────────────────────────────────────────────────

_SITE_TOOL: dict = {
    "name": "create_site",
    "description": (
        "Output the complete source files for a Next.js 14 landing page / website. "
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
                    "Complete content of app/page.tsx. Rules:\n"
                    "- First line MUST be: 'use client'\n"
                    "- Imports: react, framer-motion (motion, useInView, AnimatePresence), lucide-react icons\n"
                    "- If needs_database: also import ContactForm from '@/components/contact-form'\n"
                    "- DO NOT import from any other local file\n"
                    "- Self-contained: define all sections inline (no separate component files)\n"
                    "- Must include: sticky nav, hero with gradient/aurora, at least 3 content sections, footer\n"
                    "- Animations: use framer-motion useInView for scroll-reveal on sections\n"
                    "- Styling: use Tailwind + CSS variables (var(--accent), var(--bg), etc.)\n"
                    "- Mobile-responsive: use Tailwind responsive prefixes (sm:, md:, lg:)\n"
                    "- Premium dark-mode-first aesthetic: dark backgrounds, warm text, accent highlights"
                ),
            },
            "contact_form_tsx": {
                "type": "string",
                "description": (
                    "Complete content of components/contact-form.tsx — only when needs_database is true. "
                    "A React client component ('use client') that uses @supabase/supabase-js via @/lib/supabase. "
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
You are a senior full-stack engineer and UI designer building production-quality Next.js websites.

Your design aesthetic: dark luxury, premium, modern — like 21st.dev / Linear / Vercel's own marketing site.
Default brand tokens (use via CSS variables in globals.css):
  --bg: #0a0a0a         (near-black background)
  --surface: #141414    (card/panel background)
  --accent: #c84b31     (warm red-orange CTA)
  --text-primary: #f3ead9  (warm off-white)
  --text-muted: rgba(243,234,217,0.55)
  --border: rgba(243,234,217,0.08)

Tech stack (exact versions, already in package.json — do NOT add others):
  - Next.js 14.2.5, React 18.3.1, TypeScript 5.5.3
  - Tailwind CSS 3.4.6
  - framer-motion 11.3.28
  - lucide-react 0.417.0 (for icons)
  - @supabase/supabase-js 2.45.4 (only if needs_database)
  - clsx 2.1.1 + tailwind-merge 2.5.2 (via @/lib/utils cn())

CRITICAL BUILD RULES:
1. page.tsx MUST start with "use client" (framer-motion requires it).
2. ONLY import from: react, framer-motion, lucide-react, @/lib/utils,
   and (if needs_database) @/components/contact-form and @/lib/supabase.
   DO NOT import from any other local path.
3. All TypeScript must be valid. No implicit any. No missing props.
4. globals.css MUST have @tailwind base, @tailwind components, @tailwind utilities.
5. layout.tsx uses `export const metadata` (server component, NO "use client").
6. Every string in JSX with quotes uses &quot; or template literals — no raw " in attributes.
7. Return COMPLETE file content. No "// ... rest of component". No truncation.
"""


# ── Main generator function ───────────────────────────────────────────────────

async def generate_site(user_message: str, context: dict) -> dict:
    """
    Generate a complete Next.js site from a user prompt.
    Returns the site dict with files[], project_name, needs_database, etc.
    """
    has_db = _needs_db(user_message)
    company = context.get("company_name", "")
    industry = context.get("industry", "")

    user_prompt_parts = [f"Build request: {user_message}"]
    if company:
        user_prompt_parts.append(f"Company name: {company}")
    if industry:
        user_prompt_parts.append(f"Industry: {industry}")
    user_prompt_parts.append(
        f"needs_database: {has_db} "
        f"({'There is a form/auth/data feature — generate contact_form_tsx and migration SQL' if has_db else 'No database needed'})"
    )

    user_prompt = "\n".join(user_prompt_parts)

    try:
        async with httpx.AsyncClient(timeout=_GENERATOR_TIMEOUT) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": OPUS,
                    "max_tokens": 8192,
                    "system": _SYSTEM_PROMPT,
                    "tools": [_SITE_TOOL],
                    "tool_choice": {"type": "tool", "name": "create_site"},
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
    except Exception as e:
        print(f"site_generator: API call failed, using fallback site: {e}")
        return _fallback_site(user_message, context, has_db)

    if resp.status_code != 200:
        print(f"site_generator: API {resp.status_code}, using fallback site: {resp.text[:400]}")
        return _fallback_site(user_message, context, has_db)

    content_blocks = resp.json().get("content", [])
    tool_result: dict[str, Any] = {}
    for block in content_blocks:
        if block.get("type") == "tool_use" and block.get("name") == "create_site":
            tool_result = block.get("input", {})
            break

    if not tool_result:
        print("site_generator: model did not call create_site tool, using fallback site")
        return _fallback_site(user_message, context, has_db)

    project_name = _sanitize_name(tool_result.get("project_name", "jarvis-site"))
    needs_database = bool(tool_result.get("needs_database", has_db))
    summary = tool_result.get("summary", "")
    layout_tsx = tool_result.get("layout_tsx", "")
    globals_css = tool_result.get("globals_css", "")
    page_tsx = tool_result.get("page_tsx", "")
    contact_form_tsx = tool_result.get("contact_form_tsx", "")
    readme_md = tool_result.get("readme_md", f"# {project_name}\n\nShipped by Jarvis OS1.\n")
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
  description: "Built with Jarvis OS1",
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
    """Build-clean emergency site used when the creative generator fails."""
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
  "Built cleanly by Jarvis OS1 with a deploy-ready Next.js stack",
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
        {"path": "README.md", "content": f"# {project_name}\n\nFallback site generated by Jarvis OS1.\n"},
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
