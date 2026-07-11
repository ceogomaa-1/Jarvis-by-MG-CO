"""
Dark Matter: derive the Mind's "knowledge gaps" — hollow, dashed-outline
nodes representing things Rue doesn't know yet but should. Each gap
carries a `prompt` that becomes the node_context sent to chat when the user
clicks "Give it to me ->".
"""
import os

import httpx

from backend.lib.business.bible_loader import load_bible
from backend.lib.business.connectors.registry import list_available_connectors, list_user_connections
from backend.lib.business.readiness import calculate_readiness

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

HIGH_VALUE_CONNECTORS = {"stripe", "gohighlevel", "google", "notion"}

# readiness checkpoint key -> (mind_category, label, prompt)
_CHECKPOINT_GAPS: dict[str, tuple[str, str, str]] = {
    "name_known": ("people", "Your name", "What's your name? I'd love to know who I'm working with."),
    "business_known": ("people", "What you do", "Tell me about your business — what do you actually do day to day?"),
    "business_name": ("brand", "Business name", "What's the name of your business?"),
    "revenue_context": ("revenue", "Revenue picture", "What does your revenue look like right now — roughly, monthly or annually?"),
    "north_star_set": ("revenue", "Your north star", "If you had to pick ONE number to grow this year, what would it be?"),
    "first_connector": ("tools", "First connection", "Which tool do you use most for running your business? Let's connect it."),
    "power_connected": ("tools", "Power tools connected", "Let's connect a couple more of your tools so I can actually help with day-to-day work."),
    "five_memories": ("operations", "Getting to know your operations", "What does a typical day in your business look like?"),
    "deep_knowledge": ("operations", "Deeper operations picture", "Walk me through how a customer goes from finding you to becoming a paying client."),
}

# bible section key -> (mind_category, label, prompt)
_BIBLE_SECTION_GAPS: dict[str, tuple[str, str, str]] = {
    "metrics": ("revenue", "Key metrics", "What metrics do you track most closely for your business?"),
    "operations": ("operations", "Operations details", "What's the most time-consuming part of running your business day to day?"),
    "problems": ("risk", "Common problems", "What's the most recurring problem you run into in this business?"),
    "risk_flags": ("risk", "Risk factors", "What's the thing that worries you most about this business right now?"),
    "mindset": ("people", "Your mindset & goals", "What's driving you in this business — what's the bigger goal?"),
    "identity": ("brand", "Brand identity", "How would you describe your brand's personality or voice in a few words?"),
}


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


async def _fetch_industry(user_id: str) -> str:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/business_users",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params={"user_id": f"eq.{user_id}", "select": "industry"},
            timeout=10.0,
        )
    if resp.status_code != 200:
        return ""
    rows = resp.json()
    return (rows[0].get("industry") or "") if rows else ""


async def compute_gaps(user_id: str) -> list[dict]:
    readiness = await calculate_readiness(user_id)
    checkpoints = readiness.get("checkpoints", {})

    gaps: list[dict] = []

    for key, (mind_category, label, prompt) in _CHECKPOINT_GAPS.items():
        if not checkpoints.get(key):
            gaps.append({
                "id": f"gap_checkpoint_{key}",
                "mind_category": mind_category,
                "label": label,
                "prompt": prompt,
            })

    if not checkpoints.get("deep_knowledge"):
        industry = await _fetch_industry(user_id)
        bible = load_bible(industry) if industry else None
        if bible:
            for section, (mind_category, label, prompt) in _BIBLE_SECTION_GAPS.items():
                if bible.get(section):
                    gaps.append({
                        "id": f"gap_bible_{section}",
                        "mind_category": mind_category,
                        "label": label,
                        "prompt": prompt,
                    })

    available = list_available_connectors()
    connected = await list_user_connections(user_id)
    connected_types = {c.get("connector_type") for c in connected}
    for connector in available:
        ctype = connector.get("type")
        if ctype in HIGH_VALUE_CONNECTORS and ctype not in connected_types:
            display_name = connector.get("display_name", ctype)
            gaps.append({
                "id": f"gap_connector_{ctype}",
                "mind_category": "tools",
                "label": f"Connect {display_name}",
                "prompt": f"Let's connect {display_name} so you can use it directly from chat.",
            })

    return gaps[:12]
