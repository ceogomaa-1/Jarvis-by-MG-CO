import re

# Patterns that strongly indicate a Creation request (build, generate, design, draft,
# create, produce, write the X campaign/page/report/analysis/sequence/post).
_CREATION_TRIGGERS = [
    r"\b(build|generate|create|design|draft|produce|write|make|launch|put together)\b.{0,40}\b(campaign|landing page|landing-page|website|funnel|email sequence|drip|sms sequence|cold email|ad set|ads?|creative|copy|report|analysis|audit|deck|presentation|proposal|pitch|one[- ]?pager|brochure|menu|flyer|signage|poster|post|carousel|content calendar|brand|persona|playbook|sop|standard operating procedure)\b",
    r"^\s*(build|generate|create|design|draft|produce|write|make)\s+(me\s+|us\s+)?(a|an|the|some)\s+",
    r"\brun (a|an|the) (competitor|market|swot|customer|brand) (analysis|audit|scan|research)\b",
    r"\bspin up\b",
    r"\bship (me|us) (a|an|the)\b",
    r"\bput together\b",
]

# Patterns that BLOCK creation routing — these are chat, opinion, or Show Me How territory.
_CREATION_BLOCKLIST = [
    r"^\s*(what|which|why|when|where|who|tell me|explain|should i|should we)\b",
    r"\bhow do i\b",
    r"\bhow to\b",
    r"\bshow me how\b",
    r"\bwalk me through\b",
    r"\bstep[- ]by[- ]step\b",
]


def detect_creation(message: str) -> bool:
    """
    Returns True if the message is a multi-step Creation request that should be
    routed to the orchestrator instead of regular chat or Show Me How.
    """
    if not message or not message.strip():
        return False
    text = message.strip()

    # Blocklist wins — these are chat or Show Me How
    for pat in _CREATION_BLOCKLIST:
        if re.search(pat, text, re.IGNORECASE):
            return False

    # Trigger pass — must match at least one creation trigger
    for pat in _CREATION_TRIGGERS:
        if re.search(pat, text, re.IGNORECASE):
            return True

    return False
