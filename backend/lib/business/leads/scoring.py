"""Scoring engine — turn a normalized lead into {score 0-100, tier A/B/C, why, pitch}.

Pure + deterministic; all knobs live in config.WEIGHTS / thresholds so the rubric is tunable
in one place. The thesis: call-dependent local business + real revenue signals + weak digital
presence = a hot lead, because that's exactly who needs MG&CO's Premium Website + AI Receptionist.
"""
from urllib.parse import urlparse

from backend.lib.business.leads import config


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip("www.")
    except Exception:
        return ""


def is_weak_website(url: str | None) -> bool:
    """True if the 'website' is really a social/aggregator page (a weak digital presence)."""
    if not url:
        return False
    host = _host(url)
    return any(h in host for h in config.WEAK_WEBSITE_HOSTS)


def is_call_dependent(lead: dict) -> bool:
    hay = " ".join(lead.get("types") or []).lower() + " " + (lead.get("category") or "").lower()
    return any(t in hay for t in config.CALL_DEPENDENT_TYPES)


def is_b2c_excluded(lead: dict) -> bool:
    hay = " ".join(lead.get("types") or []).lower() + " " + (lead.get("category") or "").lower()
    return any(t in hay for t in config.EXCLUDE_TYPES)


def _real_revenue_points(review_count: int, full: int) -> int:
    if review_count < config.REVIEWS_MIN:
        return 0
    if review_count >= config.REVIEWS_STRONG:
        return full
    span = config.REVIEWS_STRONG - config.REVIEWS_MIN
    return round(full * (review_count - config.REVIEWS_MIN) / span) if span > 0 else full


def tier_for(score: int) -> str:
    if score >= config.TIER_A_MIN:
        return "A"
    if score >= config.TIER_B_MIN:
        return "B"
    return "C"


def score_lead(lead: dict, weights: dict | None = None) -> dict:
    """Score one normalized lead. Returns {score, tier, signals, why, pitch}."""
    w = weights or config.WEIGHTS
    website = lead.get("website")
    review_count = int(lead.get("review_count") or 0)
    rating = lead.get("rating")
    call_dep = is_call_dependent(lead)
    weak_site = is_weak_website(website)
    no_site = not website
    decent_rating = bool(rating and config.RATING_DECENT_MIN <= float(rating) <= config.RATING_DECENT_MAX)

    signals: dict[str, int] = {}
    if no_site:
        signals["no_website"] = w["no_website"]
    elif weak_site:
        signals["weak_website"] = w["weak_website"]
    if call_dep:
        signals["call_dependent"] = w["call_dependent"]
    rev_pts = _real_revenue_points(review_count, w["real_revenue"])
    if rev_pts:
        signals["real_revenue"] = rev_pts
    if decent_rating:
        signals["decent_rating"] = w["decent_rating"]
    if not lead.get("has_hours"):
        signals["missing_hours"] = w["missing_hours"]
    if not lead.get("phone"):
        signals["no_phone"] = w["no_phone"]

    score = max(0, min(100, sum(signals.values())))
    tier = tier_for(score)
    why, pitch = _why_and_pitch(lead, no_site, weak_site, call_dep, review_count, rating, rev_pts)
    return {"score": score, "tier": tier, "signals": signals, "why": why, "pitch": pitch}


def _why_and_pitch(lead, no_site, weak_site, call_dep, review_count, rating, rev_pts) -> tuple[str, str]:
    """One-line 'why this is a lead + what to pitch', mapping the gap → MG&CO service."""
    services: list[str] = []
    gaps: list[str] = []
    if no_site:
        gaps.append("no website")
        services.append("Premium Website")
    elif weak_site:
        gaps.append("only a social page")
        services.append("Premium Website rebuild")
    if call_dep and (no_site or not lead.get("has_hours")):
        services.append("AI Receptionist")
    if not lead.get("has_hours"):
        gaps.append("no hours listed")
    if not lead.get("phone"):
        gaps.append("no phone on listing")

    rev_bit = ""
    if review_count:
        stars = f" {rating}★" if rating else ""
        strength = "strong" if rev_pts and rev_pts >= config.WEIGHTS["real_revenue"] else "real"
        rev_bit = f"{review_count} reviews{stars} ({strength} revenue signal)"

    gap_str = ", ".join(gaps) if gaps else "solid digital presence"
    pitch = " + ".join(dict.fromkeys(services)) if services else "Audit / retainer (no obvious gap)"
    why_parts = [p for p in (gap_str, rev_bit) if p]
    why = f"{'; '.join(why_parts)} → pitch {pitch}"
    return why, pitch
