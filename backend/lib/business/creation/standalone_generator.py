"""
Standalone page generator for Jarvis OS1 — the DEFAULT "make me a landing page" path.

Produces ONE self-contained, animated, downloadable HTML file. No GitHub/Vercel required;
no build step. It is ALLOWED (and expected) to use CDN scripts, real fonts, Tailwind CDN,
and Motion/GSAP.

Returns:
  {
    "title": str,            # short human title
    "project_name": str,     # kebab-case slug
    "summary": str,          # 1-2 sentence plain-language description
    "html": str,             # the complete <!DOCTYPE html> … document
    "is_fallback": False,    # retained for wire compatibility; garbage fallbacks are forbidden
  }

The model call uses a forced tool and Anthropic's streaming SDK so long Opus generations do not
die on an idle HTTP read timeout. Every artifact passes a strict quality/identity gate before it
can be previewed, persisted, downloaded, or deployed. A failed generation is reported as a
failure; it is never replaced with a generic page and called "done".
"""
import os
import re
from typing import Any

from anthropic import AsyncAnthropic

from backend.lib.business.model_router import OPUS
from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.creation.sub_agents import _PREMIUM_DESIGN_SYSTEM
from backend.lib.business.creation.website_quality import (
    extract_client_name,
    should_use_owner_company,
    validate_standalone_html,
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_GENERATOR_TIMEOUT = 300.0
_GENERATOR_MAX_TOKENS = 24_000
try:
    # A full second Opus draft can nearly double one website's cost. Keep retries opt-in; the
    # Anthropic SDK still retries transient transport/rate-limit failures once.
    _GENERATION_ATTEMPTS = max(
        1, min(int(os.getenv("JARVIS_WEBSITE_GENERATION_ATTEMPTS", "1")), 2)
    )
except ValueError:
    _GENERATION_ATTEMPTS = 1


class WebsiteGenerationError(RuntimeError):
    """Raised when no website artifact survives generation and quality gates."""

_SYSTEM_PROMPT = (
    "You are a world-class product designer and front-end engineer. You craft single-file landing "
    "pages with the craft of a top independent digital studio. The bar is \"astonishing and "
    "modern\", never merely \"valid HTML\".\n"
    + _PREMIUM_DESIGN_SYSTEM
    + """
You are building ONE self-contained .html file. You ARE allowed scripts, CDNs, and real fonts.

IDENTITY AND ARTIFACT BOUNDARY (NON-NEGOTIABLE):
- The PRIMARY BUILD BRIEF names the target business. Build for that business, not for the account
  owner, MG&CO, Jarvis, or the chat application.
- Never reproduce the user's instruction, conversation, prompt, chat bubbles, Jarvis controls,
  "Live Preview" UI, or any app chrome inside the website.
- Never put "Built with Jarvis", "Jarvis OS1", or MG&CO attribution in client-facing copy.
- If current-site research is supplied, preserve its verified facts (offerings, location, hours,
  contact details) while completely rethinking the presentation. Never invent awards, ratings,
  customer counts, prices, addresses, or testimonials.

MANDATORY STACK (all via CDN — no build step, everything inlined into the single file):
- Tailwind via Play CDN: <script src="https://cdn.tailwindcss.com"></script>, with an inline
  `tailwind.config = {...}` <script> that extends colors with the design tokens and sets fontFamily.
- Real Google Fonts (<link>): a characterful display face for headings + a clean body face. Never
  ship system-ui as the headline font.
- Motion: GSAP 3 + ScrollTrigger via CDN
  (https://cdn.jsdelivr.net/npm/gsap@3.15/dist/gsap.min.js and
   https://cdn.jsdelivr.net/npm/gsap@3.15/dist/ScrollTrigger.min.js)
  OR Motion for JavaScript. Use it for hero entrance, scroll-reveals, staggered children,
  number count-ups, hover micro-interactions, and subtle parallax. Gate all non-essential motion
  behind `@media (prefers-reduced-motion: reduce)` AND a JS check.
- Icons: inline SVG or Lucide CDN (https://unpkg.com/lucide@latest then lucide.createIcons()).

ART DIRECTION:
- Choose a distinctive concept from the actual business and carry it through type, color, layout,
  imagery treatment, shapes, and motion. A family restaurant should feel warm, local, sensory,
  and hospitable — not like a dark SaaS dashboard.
- Use modern patterns selectively: editorial type, bento storytelling, spotlight/aurora,
  tasteful marquee, layered cards, sticky storytelling, image mosaics, and tactile CTAs.
- Avoid the obvious AI-template fingerprint: generic "Built to..." headlines, three cards named
  Fast/Modern/Yours, fake logo strips, fake testimonials, identical rounded cards everywhere,
  neon-on-black for every industry, and empty decorative dashboards.

REQUIRED CONTENT FLOW (adapt it to the business rather than blindly copying labels): clear nav and
CTA → cinematic, specific hero → proof or useful facts → offerings/menu/services → differentiated
story or experience → conversion path → FAQ when useful → strong closing CTA → complete footer.
Use at least five substantive sections.

Write real, specific, sharp copy for the actual business in the brief — never lorem ipsum, never
[placeholder]. Omit unknown facts rather than fabricating them. Fully responsive (mobile-first),
keyboard accessible, semantic, and visually complete at 375px, 768px, and 1440px.
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
    """Generate and validate one premium HTML landing page."""
    context = dict(context or {})
    client_name = context.get("client_name") or extract_client_name(user_message)
    if client_name:
        context["client_name"] = client_name
    user_prompt = _build_user_prompt(user_message, context)

    if not ANTHROPIC_API_KEY:
        raise WebsiteGenerationError(
            "Website generation is unavailable because the Anthropic API key is not configured."
        )

    last_problem = "the model returned no usable artifact"
    repair_notes: list[str] = []
    for attempt in range(_GENERATION_ATTEMPTS):
        prompt = user_prompt
        if repair_notes:
            prompt += (
                "\n\nQUALITY-GATE RETRY: The previous draft was rejected for these reasons:\n- "
                + "\n- ".join(repair_notes)
                + "\nRegenerate the complete page from scratch and fix every issue."
            )
        try:
            tool_result = await _call_page_model(prompt)
        except Exception as exc:
            last_problem = f"{type(exc).__name__}: {str(exc) or 'stream interrupted'}"
            print(
                f"standalone_generator: streamed model attempt {attempt + 1} failed: "
                f"{last_problem}"
            )
            repair_notes = ["the model stream did not finish; return a complete, more concise page"]
            continue

        document = (tool_result.get("html") or "").strip()
        repair_notes = validate_standalone_html(document, user_message, context)
        if repair_notes:
            last_problem = "; ".join(repair_notes[:6])
            print(
                f"standalone_generator: quality gate rejected attempt {attempt + 1}: "
                f"{last_problem}"
            )
            continue

        title = (
            tool_result.get("title")
            or client_name
            or (context.get("company_name") if should_use_owner_company(user_message) else "")
            or "Landing Page"
        ).strip()
        return {
            "title": title[:120],
            "project_name": _sanitize_name(
                tool_result.get("project_name") or title or "landing-page"
            ),
            "summary": (tool_result.get("summary") or "").strip()[:400],
            "html": document,
            "is_fallback": False,
        }

    raise WebsiteGenerationError(
        "I could not produce a client-safe website that passed the quality checks. "
        f"Nothing was saved or deployed. Last issue: {last_problem}"
    )


async def _call_page_model(user_prompt: str) -> dict[str, Any]:
    """Use Anthropic streaming so long Opus outputs cannot hit an idle read timeout."""
    client = AsyncAnthropic(
        api_key=ANTHROPIC_API_KEY,
        timeout=_GENERATOR_TIMEOUT,
        max_retries=1,
    )
    async with client.messages.stream(
        model=OPUS,
        max_tokens=_GENERATOR_MAX_TOKENS,
        system=[{
            "type": "text",
            "text": _SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[{**_PAGE_TOOL, "cache_control": {"type": "ephemeral"}}],
        tool_choice={"type": "tool", "name": "create_page"},
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        message = await stream.get_final_message()

    usage = UsageAccumulator(OPUS)
    usage.add_sdk_usage(getattr(message, "usage", None))
    print(f"[WEBSITE_GENERATION] {usage.log_line()}")

    for block in message.content:
        if block.type == "tool_use" and block.name == "create_page":
            return dict(block.input or {})
    raise WebsiteGenerationError("Opus completed without returning the required website artifact.")


def _build_user_prompt(user_message: str, context: dict) -> str:
    client_name = context.get("client_name") or ""
    owner_company = context.get("company_name") or ""
    parts = [
        "PRIMARY BUILD BRIEF (instructions only — never render this text verbatim):",
        user_message.strip(),
    ]
    if client_name:
        parts.extend(
            [
                "",
                f"TARGET BUSINESS (the website brand): {client_name}",
            ]
        )
    elif owner_company and should_use_owner_company(user_message):
        parts.extend(["", f"TARGET BUSINESS: {owner_company}"])

    if context.get("industry"):
        parts.append(f"Known industry context: {context['industry']}")
    if context.get("crm_context"):
        parts.extend(["", "VERIFIED CRM CONTEXT:", str(context["crm_context"])[:4_000]])
    if context.get("website_url"):
        parts.append(f"CURRENT WEBSITE URL: {context['website_url']}")
    if context.get("website_research"):
        parts.extend(
            [
                "",
                (
                    "WEB SEARCH CONTEXT (use only clearly attributable facts; omit anything "
                    "ambiguous or conflicting):"
                    if context.get("research_is_search_only")
                    else "VERIFIED CURRENT-WEBSITE RESEARCH (facts to preserve, design to surpass):"
                ),
                str(context["website_research"])[:30_000],
            ]
        )
    elif context.get("website_research_error"):
        parts.append(
            "The current website could not be read. Do not invent details that were not in the "
            "primary brief or CRM context."
        )

    if owner_company and client_name and owner_company.lower() != client_name.lower():
        parts.extend(
            [
                "",
                f"ACCOUNT OWNER (context only, NEVER the website brand): {owner_company}",
            ]
        )
    parts.extend(
        [
            "",
            "Deliver one complete, distinctive, fully animated, self-contained landing page. "
            "Return only the forced create_page tool payload.",
        ]
    )
    return "\n".join(parts)


def _sanitize_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9-]", "-", (name or "").lower())
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:40] or "landing-page"
