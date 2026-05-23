import os
from supabase import create_client

from backend.lib.business.bible_loader import load_bible
from backend.lib.business.intent_classifier import classify_intent

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

_BASE_TEMPLATE = """\
You are Jarvis for Business — an expert AI advisor for business owners. \
You answer any question that helps someone run, grow, or operate their business. \
You are direct, knowledgeable, and never refuse a legitimate business question.

You serve {company_name}, a {industry} business. The owner's role is {role}.

The following industry-specific context defines how you respond:

{bible_sections}

FORMATTING RULES:
- Use clean markdown: ## headers, **bold** for emphasis, bullet points for lists
- Keep paragraphs short (2-4 sentences max)
- Lead with the most important point first
- No corporate jargon. Talk like a veteran operator."""

_GENERIC_SYSTEM = """\
You are Jarvis for Business — an expert AI advisor for business owners and \
operators. You answer any question that helps someone run, grow, or operate \
their business — from trades to restaurants to professional services. \
You are direct, practical, and specific. Give concrete answers, not generic advice.

FORMATTING: Use clean markdown — ## headers, **bold** for key terms, bullet points. \
Short paragraphs. Lead with the most important point first."""


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _fetch_user_profile(user_id: str) -> dict:
    """Fetch company_name, industry, role from business_users. Returns {} on miss."""
    try:
        sb = _get_supabase()
        if not sb:
            return {}
        res = (
            sb.table("business_users")
            .select("company_name, industry, role")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return res.data or {}
    except Exception:
        return {}


def build_system_prompt(user_id: str, user_message: str) -> str:
    """
    Build the full system prompt for a business chat message.
    Falls back to generic system prompt if no industry profile exists.
    """
    profile = _fetch_user_profile(user_id) if user_id else {}

    industry = profile.get("industry", "")
    company_name = profile.get("company_name", "your business")
    role = profile.get("role", "owner")

    # No industry → use the generic fallback
    if not industry:
        return _GENERIC_SYSTEM

    bible = load_bible(industry)
    # Industry exists in DB but we don't have a Bible for it yet → generic
    if not bible:
        return _GENERIC_SYSTEM.replace(
            "You are Jarvis for Business",
            f"You are Jarvis for Business, advising {company_name} ({industry}). You are Jarvis for Business",
        )

    # Classify which sections to load
    section_keys = classify_intent(user_message)

    # Stitch selected sections together
    section_parts = []
    for key in section_keys:
        content = bible.get(key)
        if content:
            section_parts.append(content)

    bible_sections = "\n\n---\n\n".join(section_parts) if section_parts else ""

    return _BASE_TEMPLATE.format(
        company_name=company_name,
        industry=industry,
        role=role,
        bible_sections=bible_sections,
    )


def get_industry_context_note(user_id: str) -> str:
    """
    Returns a short note like "The user runs a Dental business."
    Used for injecting industry context into walkthrough prompts.
    """
    profile = _fetch_user_profile(user_id) if user_id else {}
    industry = profile.get("industry", "")
    if not industry:
        return ""
    return (
        f"The user runs a {industry} business. "
        f"If the walkthrough topic is industry-specific, frame it for {industry} context."
    )
