import json
import os
from datetime import datetime, timezone

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


async def save_skill(user_id: str, skill_name: str, content: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/user_skills",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates",
                },
                json={
                    "user_id": user_id,
                    "skill_name": skill_name,
                    "content": content,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10.0,
            )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"SKILLS: Error saving skill: {e}")
        return False


async def get_skills(user_id: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_skills",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
                params={
                    "user_id": f"eq.{user_id}",
                    "order": "updated_at.desc",
                },
                timeout=10.0,
            )
        return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"SKILLS: Error getting skills: {e}")
        return []


async def get_skills_summary(user_id: str) -> str:
    skills = await get_skills(user_id)
    if not skills:
        return ""
    lines = ["LEARNED PATTERNS:"]
    for s in skills[:10]:
        lines.append(f"- [{s['skill_name']}]: {s['content'][:200]}")
    return "\n".join(lines)


async def extract_and_save_skills(user_id: str, conversation: list[dict]) -> bool:
    """Analyze a conversation and extract reusable skill patterns."""
    if len(conversation) < 6:
        return False

    print(f"SKILLS: Extracting skills for user {user_id}")

    from backend.llm import jarvis_think

    convo_text = "\n".join([
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in conversation[-20:]
    ])

    extraction_prompt = f"""Analyze this conversation and extract 1-3 reusable behavioral patterns or skills about how to interact with this user.

Conversation:
{convo_text}

Return ONLY a JSON array of skill objects. Each object has:
- "skill_name": short snake_case identifier (e.g. "prefers_direct_answers", "communication_style")
- "content": one sentence describing the pattern (e.g. "User prefers very direct, short answers without padding.")

Focus on HOW the user thinks and communicates, not facts about their life.
If nothing meaningful, return empty array: []
Return ONLY valid JSON, no markdown."""

    try:
        raw = await jarvis_think(
            user_message=extraction_prompt,
            conversation_history=[],
            system_override="You are a behavioral pattern extractor. Return only valid JSON arrays. No markdown, no explanation.",
        )
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        skills = json.loads(raw)

        if not isinstance(skills, list):
            return False

        for skill in skills:
            if "skill_name" in skill and "content" in skill:
                await save_skill(user_id, skill["skill_name"], skill["content"])
                print(f"SKILLS: Saved skill '{skill['skill_name']}' for {user_id}")

        return True
    except Exception as e:
        print(f"SKILLS: Extraction failed: {e}")
        return False
