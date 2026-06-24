"""
Provider resolver — decides which brain answers, per mode.

HARD RULE: every mode is pinned to Claude EXCEPT Study Mode. Study Mode reads a
flag; everything else is unconditional Claude and no flag can change it. The
default for any unknown/other mode is always Claude, so a misroute is impossible.

Toggle surface:
  - STUDY_MODE_PROVIDER env: "claude" (default) | "grok". Anything other than the
    literal "grok" → Claude.
  - GROK_API_KEY env: required for grok. If provider=grok but the key is missing,
    we fail safe to Claude and return a notice (never crash Study Mode).
  - Optional per-request override (the in-app toggle) takes precedence over the
    env value for that one session, but is subject to the same key check.
"""
import os

CLAUDE = "claude"
GROK = "grok"


def grok_configured() -> bool:
    """True when a Grok key is present (non-empty). Validity is proven at call time."""
    return bool((os.getenv("GROK_API_KEY") or "").strip())


def resolve_study_provider(request_override: str | None = None) -> tuple[str, str | None]:
    """Resolve the Study Mode brain.

    Returns (provider, notice):
      provider — "claude" or "grok"
      notice   — a short user-facing string when we fell back to Claude, else None.

    Precedence: explicit per-request override > STUDY_MODE_PROVIDER env > "claude".
    Fails safe to Claude whenever Grok isn't both requested AND configured.
    """
    want = (request_override or os.getenv("STUDY_MODE_PROVIDER") or "").strip().lower()
    if want != GROK:
        return CLAUDE, None
    if not grok_configured():
        return CLAUDE, "Grok isn't configured yet — staying on the default brain."
    return GROK, None


def provider_for_mode(mode: str, study_override: str | None = None) -> str:
    """Provider for a named mode. Only 'study' can ever be non-Claude.

    Every other mode (personal, business, crm, leads, onboarding, …) and any
    unknown mode resolves to Claude unconditionally.
    """
    if mode == "study":
        return resolve_study_provider(study_override)[0]
    return CLAUDE
