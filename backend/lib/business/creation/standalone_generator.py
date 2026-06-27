"""
Standalone page generator for Jarvis OS1 — the DEFAULT "make me a landing page" path.

Produces ONE self-contained, animated, downloadable HTML file. No GitHub/Vercel required;
no build step. It is ALLOWED (and expected) to use CDN scripts, Google Fonts, Tailwind CDN,
and Motion/GSAP — that is what makes the output "astonishing and modern".

Returns:
  {
    "title": str,            # short human title
    "project_name": str,     # kebab-case slug
    "summary": str,          # 1-2 sentence plain-language description
    "html": str,             # the complete <!DOCTYPE html> … document
    "is_fallback": bool,     # True if the model call failed and this is the emergency template
  }

The model call uses a forced tool so we always get clean, complete HTML (no code fences, no
preamble). If the API is unavailable, _fallback_page() returns a genuinely premium template so
the pipeline NEVER hard-fails and tests run offline.
"""
import os
import re
from typing import Any

import httpx

from backend.lib.business.model_router import OPUS
from backend.lib.business.creation.sub_agents import _PREMIUM_DESIGN_SYSTEM

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GENERATOR_TIMEOUT = 60.0

_SYSTEM_PROMPT = (
    "You are a world-class product designer and front-end engineer. You craft single-file landing "
    "pages that win awards — the calibre of Linear, Stripe, Vercel, Aceternity. The bar is "
    "\"astonishing and modern\", never \"valid HTML\".\n"
    + _PREMIUM_DESIGN_SYSTEM
    + """
You are building ONE self-contained .html file. You ARE allowed scripts, CDNs, and real fonts.

MANDATORY STACK (all via CDN — no build step, everything inlined into the single file):
- Tailwind via Play CDN: <script src="https://cdn.tailwindcss.com"></script>, with an inline
  `tailwind.config = {...}` <script> that extends colors with the design tokens and sets fontFamily.
- Real Google Fonts (<link>): a characterful display face for headings + a clean body face. Never
  ship system-ui as the headline font.
- Motion: GSAP 3 + ScrollTrigger via CDN
  (https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js and
   https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js)
  OR Motion One. Use it for hero entrance, scroll-reveals on every section, staggered children,
  number count-ups, magnetic/hover micro-interactions, subtle parallax. Gate all non-essential
  motion behind `@media (prefers-reduced-motion: reduce)` AND a JS check.
- Icons: inline SVG or Lucide CDN (https://unpkg.com/lucide@latest then lucide.createIcons()).

REQUIRED SECTIONS (adapt to the business): sticky glass nav w/ CTA → cinematic hero (oversized
clamp() headline, gradient/aurora/spotlight backdrop, primary + ghost CTA, trust strip) →
logo marquee or stats bar → bento or 3-up features w/ hover lift → how-it-works/showcase →
testimonials → pricing (if relevant) → FAQ accordion → big closing CTA → footer.

Write real, specific, sharp copy for the actual business in the brief — never lorem ipsum, never
[placeholder] unless a hard fact is genuinely unknown. Fully responsive (mobile-first).
"""
)

_PAGE_TOOL = {
    "name": "create_page",
    "description": (
        "Return the ONE complete, self-contained HTML landing page. The `html` field must contain "
        "the entire document from <!DOCTYPE html> to </html> — all CSS, all scripts, all markup "
        "inlined. No truncation, no TODOs, no markdown fences."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short human title for the page (e.g. 'Brightsmile Dental')."},
            "project_name": {"type": "string", "description": "kebab-case slug, lowercase + hyphens, max 40 chars."},
            "summary": {"type": "string", "description": "1-2 sentence plain-language description of the page."},
            "html": {
                "type": "string",
                "description": (
                    "The COMPLETE single-file HTML document. Starts with <!DOCTYPE html>. Includes the "
                    "Tailwind CDN + inline config, Google Fonts <link>s, GSAP/Motion CDN + init scripts, "
                    "design-token CSS, and every section filled with real copy. Self-contained and "
                    "openable as a file with zero dependencies beyond the CDNs."
                ),
            },
        },
        "required": ["title", "project_name", "summary", "html"],
    },
}


async def generate_standalone_page(user_message: str, context: dict) -> dict:
    """Generate a single premium HTML landing page from the user's prompt."""
    company = (context or {}).get("company_name", "")
    industry = (context or {}).get("industry", "")

    parts = [f"Build request: {user_message}"]
    if company:
        parts.append(f"Company name: {company}")
    if industry:
        parts.append(f"Industry: {industry}")
    parts.append(
        "Deliver one astonishing, fully-animated, self-contained landing page. Make it feel alive "
        "and premium — the kind of page that makes people screenshot it."
    )
    user_prompt = "\n".join(parts)

    if not ANTHROPIC_API_KEY:
        return _fallback_page(user_message, context)

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
                    "max_tokens": 16000,
                    "system": _SYSTEM_PROMPT,
                    "tools": [_PAGE_TOOL],
                    "tool_choice": {"type": "tool", "name": "create_page"},
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
    except Exception as e:
        print(f"standalone_generator: API call failed, using fallback: {e}")
        return _fallback_page(user_message, context)

    if resp.status_code != 200:
        print(f"standalone_generator: API {resp.status_code}, using fallback: {resp.text[:300]}")
        return _fallback_page(user_message, context)

    tool_result: dict[str, Any] = {}
    for block in resp.json().get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "create_page":
            tool_result = block.get("input", {})
            break

    html = (tool_result.get("html") or "").strip()
    if not html or "<" not in html:
        print("standalone_generator: model returned no usable html, using fallback")
        return _fallback_page(user_message, context)

    title = (tool_result.get("title") or company or "Landing Page").strip()
    return {
        "title": title[:120],
        "project_name": _sanitize_name(tool_result.get("project_name") or title or "landing-page"),
        "summary": (tool_result.get("summary") or "").strip()[:400],
        "html": html,
        "is_fallback": False,
    }


def _sanitize_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9-]", "-", (name or "").lower())
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:40] or "landing-page"


def _fallback_page(user_message: str, context: dict) -> dict:
    """Emergency template — still genuinely premium so a failed API call never ships garbage."""
    company = (context or {}).get("company_name") or "Your Brand"
    headline = (user_message or "Something remarkable").strip()[:80]
    html = _FALLBACK_HTML.replace("{{COMPANY}}", company).replace("{{HEADLINE}}", headline)
    return {
        "title": company,
        "project_name": _sanitize_name(company),
        "summary": "A premium dark-luxury landing page scaffold (generated offline fallback).",
        "html": html,
        "is_fallback": True,
    }


_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{{COMPANY}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    theme: { extend: {
      colors: { bg:'#0a0a0a', surface:'#141414', accent:'#c84b31', accent2:'#e88a5a', text:'#f3ead9' },
      fontFamily: { display:['Sora','sans-serif'], body:['Inter','sans-serif'] },
    } }
  }
</script>
<style>
  :root { --accent:#c84b31; --accent2:#e88a5a; }
  body { background:#0a0a0a; color:#f3ead9; font-family:'Inter',sans-serif; }
  .display { font-family:'Sora',sans-serif; }
  .aurora { background:
      radial-gradient(60% 50% at 20% 10%, rgba(200,75,49,0.20), transparent 60%),
      radial-gradient(50% 40% at 85% 20%, rgba(232,138,90,0.15), transparent 60%); }
  .reveal { opacity:0; transform:translateY(28px); transition:opacity .8s cubic-bezier(.2,.7,.2,1), transform .8s cubic-bezier(.2,.7,.2,1); }
  .reveal.in { opacity:1; transform:none; }
  @media (prefers-reduced-motion: reduce){ .reveal{opacity:1;transform:none;transition:none;} }
</style>
</head>
<body class="antialiased">
  <header class="sticky top-0 z-50 backdrop-blur-xl bg-black/40 border-b border-white/10">
    <nav class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
      <span class="display font-extrabold tracking-tight text-lg">{{COMPANY}}</span>
      <a href="#cta" class="rounded-full px-5 py-2 text-sm font-semibold text-black" style="background:var(--accent)">Get started</a>
    </nav>
  </header>

  <section class="relative overflow-hidden aurora">
    <div class="max-w-5xl mx-auto px-6 py-32 text-center reveal">
      <p class="uppercase tracking-[0.25em] text-xs mb-6" style="color:var(--accent2)">{{HEADLINE}}</p>
      <h1 class="display font-extrabold leading-[1.02]" style="font-size:clamp(40px,8vw,88px)">
        Built to make<br>an unforgettable<span style="color:var(--accent)"> impression</span>.
      </h1>
      <p class="mt-8 text-lg md:text-xl text-white/60 max-w-2xl mx-auto">
        A premium experience for {{COMPANY}} — fast, modern, and crafted to convert.
      </p>
      <div class="mt-10 flex items-center justify-center gap-4">
        <a href="#cta" class="rounded-xl px-7 py-3.5 font-semibold text-black shadow-lg" style="background:var(--accent)">Start now</a>
        <a href="#features" class="rounded-xl px-7 py-3.5 font-semibold border border-white/15 hover:border-white/30 transition">Learn more</a>
      </div>
    </div>
  </section>

  <section id="features" class="max-w-6xl mx-auto px-6 py-28 grid md:grid-cols-3 gap-6">
    <div class="reveal rounded-2xl p-8 bg-white/[0.03] border border-white/10 hover:-translate-y-1 transition">
      <h3 class="display text-xl font-bold mb-3">Crafted</h3>
      <p class="text-white/55">Every pixel considered — typography, spacing, and motion in harmony.</p>
    </div>
    <div class="reveal rounded-2xl p-8 bg-white/[0.03] border border-white/10 hover:-translate-y-1 transition">
      <h3 class="display text-xl font-bold mb-3">Fast</h3>
      <p class="text-white/55">Single-file, instant-loading, and effortless to share or deploy.</p>
    </div>
    <div class="reveal rounded-2xl p-8 bg-white/[0.03] border border-white/10 hover:-translate-y-1 transition">
      <h3 class="display text-xl font-bold mb-3">Yours</h3>
      <p class="text-white/55">Tuned to your brand and ready to take live in one click.</p>
    </div>
  </section>

  <section id="cta" class="max-w-4xl mx-auto px-6 py-28 text-center reveal">
    <h2 class="display font-extrabold" style="font-size:clamp(32px,5vw,56px)">Ready when you are.</h2>
    <p class="mt-5 text-white/60 text-lg">Let's make {{COMPANY}} unforgettable.</p>
    <a href="#" class="inline-block mt-8 rounded-xl px-8 py-4 font-semibold text-black" style="background:var(--accent)">Get started</a>
  </section>

  <footer class="border-t border-white/10 py-10 text-center text-white/40 text-sm">
    © <span id="yr"></span> {{COMPANY}}. Crafted with Jarvis OS1.
  </footer>

  <script>
    document.getElementById('yr').textContent = new Date().getFullYear();
    const els = document.querySelectorAll('.reveal');
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      els.forEach(e => e.classList.add('in'));
    } else {
      const io = new IntersectionObserver((entries) => {
        entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
      }, { threshold: 0.12 });
      els.forEach(e => io.observe(e));
    }
  </script>
</body>
</html>"""
