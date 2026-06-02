import re

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-7"

# Short greetings and simple acks → Haiku (fast, cheap)
_HAIKU_PATTERNS = [
    r"^\s*(hi|hello|hey|sup|yo|good\s+morning|good\s+afternoon|good\s+evening|gm|gn|good\s+day)\s*[!?.]*\s*$",
    r"^\s*(thank\s+you|thanks|thx|ty)\s*[!?.]*\s*$",
    r"^\s*(ok|okay|ok\s+got\s+it|got\s+it|perfect|great|awesome|sure|sounds\s+good|cool|nice|noted|roger)\s*[!?.]*\s*$",
    r"^\s*(bye|goodbye|cya|see\s+you|later)\s*[!?.]*\s*$",
    r"^\s*what('?s| is)\s+(your\s+name|jarvis|this\s+app|this\s+tool)\s*[?.]?\s*$",
    r"^\s*who\s+are\s+you\s*[?.]?\s*$",
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
    Haiku for greetings, Opus for strategic work, Sonnet for everything else.
    """
    if not message or not message.strip():
        return SONNET

    text = message.strip()

    for pat in _HAIKU_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return HAIKU

    for pat in _OPUS_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return OPUS

    return SONNET
