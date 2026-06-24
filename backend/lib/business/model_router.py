import os
import re

# Model tiers are env-configurable so Mohamed can dial the cost/quality mix
# without a redeploy. Defaults match the prior hard-coded ids.
HAIKU = os.getenv("JARVIS_MODEL_CHEAP", "claude-haiku-4-5-20251001")
SONNET = os.getenv("JARVIS_MODEL_STANDARD", "claude-sonnet-4-6")
OPUS = os.getenv("JARVIS_MODEL_SMART", "claude-opus-4-8")

# Master switch: set JARVIS_MODEL_TIERING=0 to force every turn onto SONNET
# (the old default behaviour) if tiering ever misroutes.
_TIERING_ON = os.getenv("JARVIS_MODEL_TIERING", "1") != "0"

# Short greetings and simple acks → Haiku (fast, cheap)
_HAIKU_PATTERNS = [
    r"^\s*(hi|hello|hey|sup|yo|good\s+morning|good\s+afternoon|good\s+evening|gm|gn|good\s+day)\s*[!?.]*\s*$",
    r"^\s*(thank\s+you|thanks|thx|ty)\s*[!?.]*\s*$",
    r"^\s*(ok|okay|ok\s+got\s+it|got\s+it|perfect|great|awesome|sure|sounds\s+good|cool|nice|noted|roger)\s*[!?.]*\s*$",
    r"^\s*(bye|goodbye|cya|see\s+you|later)\s*[!?.]*\s*$",
    r"^\s*what('?s| is)\s+(your\s+name|jarvis|this\s+app|this\s+tool)\s*[?.]?\s*$",
    r"^\s*who\s+are\s+you\s*[?.]?\s*$",
]

# Mechanical / high-volume work that does NOT need Opus-grade reasoning →
# Haiku. This is the cost lever for the expensive case in the brief: a bulk CRM
# edit ("set Status on 38 companies") is tool-routing + formatting, not strategy,
# yet it was billing at Sonnet/Opus rates across many round-trips. Routing it to
# Haiku (with prompt caching on top) is the bulk of the savings.
_CHEAP_PATTERNS = [
    # CRM CRUD / bulk record edits
    r"\b(set|update|change|mark|flag|assign|fill\s+in|fill\s+out)\b.*\b(status|stage|field|tag|owner|value|column|all|every|each|these|those)\b",
    r"\bbulk\b",
    r"\b(add|push|import|sync)\b.*\b(to\s+(my\s+)?crm|to\s+(my\s+)?pipeline|companies|contacts|leads)\b",
    r"\b(re-?home|move)\b.*\bfield\b",
    r"\bset\s+status\b",
    r"\bmark\s+(all|them|these|those|as)\b",
    # Lead prospecting / scoring (deterministic tool work)
    r"\b(find|get|pull|prospect|score)\b.*\bleads?\b",
    r"\bfind\s+(me\s+)?(businesses|companies|salons|restaurants|clinics|realtors|agents)\b",
    # List / lookup / formatting requests
    r"^\s*(list|show|count|how\s+many|which|what)\b.*\b(crm|contacts|companies|opportunities|deals|leads|pipeline|stage)\b",
    r"\b(format|reformat|tidy\s+up|clean\s+up|tabulate|summari[sz]e\s+(this|the)\s+(list|table|data))\b",
]

# Strategic / heavy analytical requests → Opus (best quality)
_OPUS_PATTERNS = [
    r"\b(strategic\s+plan|business\s+plan|growth\s+strategy|go[- ]to[- ]market|gtm\s+strategy)\b",
    r"\b(market\s+analysis|competitor\s+analysis|competitive\s+analysis|swot\s+analysis|market\s+research)\b",
    r"\b(financial\s+model|unit\s+economics|valuation|cap\s+table|revenue\s+model|pricing\s+strategy)\b",
    r"\b(acquisition\s+strategy|merger|acquisition|exit\s+strategy|ipo|fundraising|series\s+[a-z]|venture\s+capital|private\s+equity)\b",
    r"\b(deep\s+dive|comprehensive\s+analysis|full\s+audit|detailed\s+breakdown|thorough\s+review)\b",
    r"\b(5[- ]year|ten[- ]year|10[- ]year|annual\s+plan|quarterly\s+plan|long[- ]term\s+strategy)\b",
    r"\b(restructure|overhaul|business\s+transformation|turnaround|pivot|rebrand)\b",
    r"\b(investor\s+deck|pitch\s+deck|board\s+deck|vc\s+presentation|investor\s+presentation)\b",
]


def select_model(message: str) -> str:
    """
    Route to the cheapest model that can handle the required quality.

    Order matters: greetings → Haiku, then explicit strategic work → Opus, then
    mechanical CRUD/bulk/lookup/formatting → Haiku, else Sonnet. Opus is checked
    before the cheap patterns so a genuinely strategic request that happens to
    mention "companies" still gets the strong model.
    """
    if not message or not message.strip():
        return SONNET

    text = message.strip()

    for pat in _HAIKU_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return HAIKU

    if not _TIERING_ON:
        return SONNET

    for pat in _OPUS_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return OPUS

    for pat in _CHEAP_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return HAIKU

    return SONNET


def select_personal_model(message: str) -> str:
    """Model routing for Personal Jarvis (the companion).

    Deliberately conservative: only obvious greetings/acks drop to Haiku; real
    conversation stays on Sonnet (no CRM/bulk downgrade, no Opus upgrade) so the
    companion's warmth and depth are never traded away for a few cents.
    """
    if not message or not message.strip() or not _TIERING_ON:
        return SONNET
    text = message.strip()
    for pat in _HAIKU_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return HAIKU
    return SONNET
