"""
User readiness score — how well Jarvis knows the user (0–100).
At 100 points, autonomous mode unlocks.
"""
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


def _headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _get_next_milestone(checkpoints: dict) -> str:
    if not checkpoints.get("name_known"):
        return "Tell Jarvis your name"
    if not checkpoints.get("business_known"):
        return "Tell Jarvis about your business and industry"
    if not checkpoints.get("business_name"):
        return "Share your business name"
    if not checkpoints.get("first_connector"):
        return "Connect at least one tool (Stripe, Gmail, Notion...)"
    if not checkpoints.get("north_star_set"):
        return "Set your North Star revenue target in Brand settings"
    if not checkpoints.get("revenue_context"):
        return "Discuss your revenue goals with Jarvis"
    if not checkpoints.get("five_memories"):
        return "Keep chatting — Jarvis is still learning about you"
    if not checkpoints.get("power_connected"):
        return "Connect 2 more tools to unlock full power"
    if not checkpoints.get("deep_knowledge"):
        return "Continue sharing context — almost there"
    return "Autonomous mode ready!"


async def calculate_readiness(user_id: str) -> dict:
    """
    Calculate how well Jarvis knows the user (0–100).
    Reads memories, connectors, brand config, and conversation count.
    """
    empty = {
        "score": 0,
        "checkpoints": {},
        "memory_count": 0,
        "connector_count": 0,
        "is_ready": False,
        "next_milestone": "Tell Jarvis your name",
    }
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return empty

    user_uuid = _user_id_to_uuid(user_id)
    score = 0
    checkpoints: dict = {}
    memory_count = 0
    connector_count = 0

    try:
        async with httpx.AsyncClient() as client:
            # 1. Memories (max 25 pts)
            mem_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_user_memories",
                headers=_headers(),
                params={"select": "memory", "user_id": f"eq.{user_uuid}"},
                timeout=10.0,
            )
            memories = mem_resp.json() if mem_resp.status_code == 200 else []
            memory_count = len(memories)
            texts = [m.get("memory", "").lower() for m in memories]

            if memory_count >= 1:
                score += 5
                checkpoints["first_memory"] = True
            if memory_count >= 5:
                score += 10
                checkpoints["five_memories"] = True
            if memory_count >= 15:
                score += 10
                checkpoints["deep_knowledge"] = True

            # 2. Name known (10 pts)
            if any("name" in t or "called" in t for t in texts):
                score += 10
                checkpoints["name_known"] = True

            # 3. Business type/industry (10 pts)
            _industries = [
                "restaurant", "dental", "salon", "real estate", "trades",
                "retail", "law", "clinic", "contractor",
            ]
            if any(any(ind in t for ind in _industries) for t in texts):
                score += 10
                checkpoints["business_known"] = True

            # 4. Business name (10 pts)
            if any(
                "business" in t and ("called" in t or "named" in t or "runs" in t)
                for t in texts
            ):
                score += 10
                checkpoints["business_name"] = True

            # 5. Revenue/goals context (10 pts)
            _revenue_kw = ["revenue", "target", "goal", "arr", "$", "monthly", "annual"]
            if any(any(w in t for w in _revenue_kw) for t in texts):
                score += 10
                checkpoints["revenue_context"] = True

            # 6. Connectors (10 pts for ≥1, another 10 pts for ≥3)
            conn_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_connectors",
                headers=_headers(),
                params={"select": "id", "user_id": f"eq.{user_uuid}", "is_active": "eq.true"},
                timeout=10.0,
            )
            connectors = conn_resp.json() if conn_resp.status_code == 200 else []
            connector_count = len(connectors)

            if connector_count >= 1:
                score += 10
                checkpoints["first_connector"] = True
            if connector_count >= 3:
                score += 10
                checkpoints["power_connected"] = True

            # 7. North Star configured (10 pts)
            brand_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_brand_config",
                headers=_headers(),
                params={
                    "select": "north_star_target_usd",
                    "user_id": f"eq.{user_uuid}",
                    "limit": "1",
                },
                timeout=10.0,
            )
            brand_rows = brand_resp.json() if brand_resp.status_code == 200 else []
            if brand_rows and brand_rows[0].get("north_star_target_usd"):
                score += 10
                checkpoints["north_star_set"] = True

            # 8. Conversation depth — ≥3 conversations (5 pts)
            conv_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/business_conversations",
                headers=_headers(),
                params={"select": "id", "user_id": f"eq.{user_uuid}"},
                timeout=10.0,
            )
            convos = conv_resp.json() if conv_resp.status_code == 200 else []
            if len(convos) >= 3:
                score += 5
                checkpoints["conversation_depth"] = True

    except Exception as e:
        print(f"READINESS: calculate error: {e}")

    score = min(score, 100)
    return {
        "score": score,
        "checkpoints": checkpoints,
        "memory_count": memory_count,
        "connector_count": connector_count,
        "is_ready": score >= 100,
        "next_milestone": _get_next_milestone(checkpoints),
    }
