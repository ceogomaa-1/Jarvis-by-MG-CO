import os
import re

_BIBLES_DIR = os.path.join(os.path.dirname(__file__), "bibles")

_INDUSTRY_FILE_MAP = {
    "restaurants": "restaurant.md",
    "restaurant": "restaurant.md",
    "real estate": "real_estate.md",
    "real_estate": "real_estate.md",
    "dental": "dental.md",
    "salon/spa": "salon_spa.md",
    "salon_spa": "salon_spa.md",
    "salon": "salon_spa.md",
    "spa": "salon_spa.md",
    "trades/contractors": "trades_contractors.md",
    "trades_contractors": "trades_contractors.md",
    "trades": "trades_contractors.md",
    "contractors": "trades_contractors.md",
    # Fitness and Auto Repair don't have bibles yet — fall back gracefully
    "fitness": None,
    "auto repair": None,
    "auto_repair": None,
}

# Maps ## header patterns → section key
_HEADER_KEY_MAP = [
    ("WHO YOU ARE", "identity"),
    ("HOW ", "operations"),          # "HOW A DENTAL PRACTICE..." / "HOW THE RESTAURANT..."
    ("THE 25 PROBLEMS", "problems"),
    ("THE METRICS", "metrics"),
    ("RISK FLAGS", "risk_flags"),
    ("GARY VEE", "mindset"),
    ("JARVIS DAILY OPERATIONS", "daily_ops"),
    ("FIRST CONVERSATION", "first_conversation"),
    ("THE MOVES NOBODY", "moves"),
]


def get_industry_filename(industry: str) -> str | None:
    """Return the bible filename for an industry string, or None if unsupported."""
    return _INDUSTRY_FILE_MAP.get(industry.lower().strip())


def load_bible(industry: str) -> dict:
    """
    Parse the industry Bible into a dict of section_key → content.
    Returns an empty dict if no Bible exists for the industry.
    """
    filename = get_industry_filename(industry)
    if not filename:
        return {}

    filepath = os.path.join(_BIBLES_DIR, filename)
    if not os.path.exists(filepath):
        return {}

    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # Split by ## headers (but not ### sub-headers)
    # Each chunk: the header line + its content until the next ## header
    chunks = re.split(r"\n(?=## )", raw)

    sections: dict[str, str] = {}
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # Extract the header text (first line)
        first_line = chunk.split("\n", 1)[0].strip()
        header_text = first_line.lstrip("#").strip().upper()

        # Match to a section key
        key = None
        for prefix, section_key in _HEADER_KEY_MAP:
            if header_text.startswith(prefix):
                key = section_key
                break

        if key:
            # Store the full chunk (header + body)
            sections[key] = chunk

    return sections
