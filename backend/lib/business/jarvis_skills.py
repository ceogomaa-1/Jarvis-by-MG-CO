"""
Jarvis Skills — user-authored, persistent, lossless.

The user feeds Jarvis material; we store it WHOLE and forever (`jarvis_skills`),
generate metadata to make it usable, and (for knowledge) chunk + embed it into the
existing pgvector store for retrieval. Two kinds:
  knowledge — things Jarvis should know / recall / cite
  behavior  — rules / procedures / personality that change how Jarvis operates
  both      — does both

The cardinal rule (the original sin this replaces): NEVER silently drop user input.
The full raw content is saved BEFORE any LLM step, and the LLM is used ONLY to add
metadata — it can never cause "nothing useful found". The only legitimate failure is
genuinely empty / unreadable content, and that is reported honestly.
"""
import json
import os

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

HAIKU = "claude-haiku-4-5-20251001"

VALID_TYPES = ("knowledge", "behavior", "both")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers() -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": "return=representation"}


# ── Pure helpers (unit-tested) ────────────────────────────────────────────────

def _fallback_name(content: str, filename: str | None) -> str:
    """A never-empty name when the LLM can't provide one: filename, else first line."""
    if filename:
        base = filename.rsplit(".", 1)[0].strip()
        if base:
            return base[:120]
    for line in (content or "").splitlines():
        line = line.lstrip("#-*> ").strip()
        if line:
            return line[:120]
    return "Untitled skill"


def _fallback_metadata(content: str, filename: str | None) -> dict:
    """Used whenever the metadata LLM call fails or returns nothing. Defaults to a
    knowledge skill named from the filename/first line — saving is never blocked."""
    return {
        "name": _fallback_name(content, filename),
        "description": "",
        "skill_type": "knowledge",
        "operating_instructions": None,
    }


def _chunk_text(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end >= n:
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _what_changes(skill_type: str, name: str) -> str:
    """One-line, concrete confirmation of how this skill will affect Jarvis."""
    if skill_type == "behavior":
        return f"Jarvis will now follow the operating rules in '{name}' on every relevant turn."
    if skill_type == "both":
        return f"Jarvis will recall '{name}' when relevant and follow its operating rules."
    return f"Jarvis will recall and cite '{name}' when your questions relate to it."


_METADATA_PROMPT = """\
A user is teaching their AI business operator a new SKILL by feeding it the material below.
Produce metadata that makes this skill usable. Do NOT summarize away or judge the content —
it is already stored verbatim; you only describe it.

Decide skill_type:
- "knowledge": reference material Jarvis should know, recall, and cite (docs, pricing, policies, facts, playbooks to reference).
- "behavior": rules/procedures/personality that should CHANGE HOW Jarvis acts (tone, greetings, process to always follow).
- "both": material that is reference AND changes behavior.

MATERIAL (source: {label}):
\"\"\"
{content}
\"\"\"

Return ONLY valid JSON, no markdown:
{{"name": "<=8 word title", "description": "one sentence: when this skill applies / what it's for (the trigger)", "skill_type": "knowledge|behavior|both", "operating_instructions": "<for behavior/both ONLY: a crisp imperative summary of how Jarvis should operate, e.g. 'Always greet clients in one short line and end with a next-step question.' For pure knowledge, use null>"}}"""


async def generate_skill_metadata(content: str, filename: str | None = None) -> dict:
    """Best-effort metadata via Haiku. ALWAYS returns a usable dict — falls back to
    safe defaults on any error so it can never block saving."""
    fallback = _fallback_metadata(content, filename)
    if not ANTHROPIC_API_KEY or not content.strip():
        return fallback
    prompt = _METADATA_PROMPT.format(label=filename or "pasted text", content=content[:12000])
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={"model": HAIKU, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]},
                timeout=30.0,
            )
        if resp.status_code != 200:
            print(f"SKILLS: metadata API error {resp.status_code}: {resp.text[:200]}")
            return fallback
        raw = resp.json().get("content", [{}])[0].get("text", "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        if not isinstance(data, dict):
            return fallback
        skill_type = data.get("skill_type")
        if skill_type not in VALID_TYPES:
            skill_type = "knowledge"
        instr = data.get("operating_instructions")
        if isinstance(instr, str) and not instr.strip():
            instr = None
        return {
            "name": (data.get("name") or fallback["name"])[:120],
            "description": (data.get("description") or "")[:1000],
            "skill_type": skill_type,
            "operating_instructions": instr if skill_type in ("behavior", "both") else None,
        }
    except Exception as e:
        print(f"SKILLS: metadata generation failed: {e}")
        return fallback


async def _embed_skill_chunks(user_id: str, skill_id: str, content: str) -> int:
    """Chunk + embed knowledge content into the existing document_chunks store, tagged
    with skill_id + user_id. Best-effort: the full content is already saved on the skill
    row, so any failure here is non-fatal (returns 0)."""
    try:
        from backend.routes.documents import _embed
    except Exception:
        return 0
    chunks = _chunk_text(content)
    if not chunks:
        return 0
    embeddings = await _embed(chunks)
    if not embeddings:
        return 0  # no embedding backend; full_content still recallable via the skill row
    stored = 0
    try:
        async with httpx.AsyncClient() as client:
            for i in range(0, len(chunks), 50):
                batch = []
                for j, chunk in enumerate(chunks[i:i + 50]):
                    batch.append({
                        "user_id": user_id,
                        "skill_id": skill_id,
                        "chunk_index": i + j,
                        "content": chunk,
                        "embedding": embeddings[i + j],
                    })
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/document_chunks",
                    headers={**_write_headers(), "Prefer": "return=minimal"},
                    json=batch,
                    timeout=30.0,
                )
                if resp.status_code in (200, 201, 204):
                    stored += len(batch)
    except Exception as e:
        print(f"SKILLS: embed chunks error: {e}")
    return stored


async def create_skill(
    user_id: str,
    full_content: str,
    *,
    source_type: str = "text",
    source_filename: str | None = None,
    name: str | None = None,
    description: str | None = None,
    skill_type: str | None = None,
    operating_instructions: str | None = None,
) -> dict:
    """
    Store a skill LOSSLESSLY. The full raw content is saved verbatim first; the LLM is
    used only to fill missing metadata. Returns a result dict — and for any non-empty
    input the status is 'learned', NEVER 'nothing useful found'.
    """
    content = (full_content or "").strip()
    if not content:
        return {"status": "error", "error": "There was no readable text to learn from.", "label": source_filename or "text"}
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {"status": "error", "error": "Supabase not configured", "label": source_filename or "text"}

    # Metadata (best-effort) — only fill what the caller didn't pin explicitly.
    meta = await generate_skill_metadata(content, source_filename)
    final_name = (name or meta.get("name") or _fallback_name(content, source_filename))[:200]
    final_type = skill_type or meta.get("skill_type") or "knowledge"
    if final_type not in VALID_TYPES:
        final_type = "knowledge"
    final_desc = (description if description is not None else meta.get("description")) or ""
    final_instr = operating_instructions if operating_instructions is not None else meta.get("operating_instructions")

    row = {
        "user_id": user_id,
        "name": final_name,
        "description": final_desc[:1000],
        "skill_type": final_type,
        "full_content": full_content,  # verbatim — never truncated
        "operating_instructions": final_instr,
        "source_type": source_type,
        "source_filename": source_filename,
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/jarvis_skills",
                headers=_write_headers(),
                json=row,
                timeout=20.0,
            )
        if resp.status_code not in (200, 201) or not resp.json():
            return {"status": "error", "error": f"Couldn't save the skill (database {resp.status_code}).", "label": final_name}
        skill_id = resp.json()[0]["id"]
    except Exception as e:
        return {"status": "error", "error": f"Couldn't save the skill: {e}", "label": final_name}

    chunks_stored = 0
    if final_type in ("knowledge", "both"):
        chunks_stored = await _embed_skill_chunks(user_id, skill_id, content)

    return {
        "status": "learned",
        "skill_id": skill_id,
        "name": final_name,
        "skill_type": final_type,
        "label": source_filename or final_name,
        "chunks": chunks_stored,
        "what_changes": _what_changes(final_type, final_name),
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def list_skills(user_id: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/jarvis_skills",
                headers=_read_headers(),
                params={"select": "*", "user_id": f"eq.{user_id}", "order": "created_at.desc"},
                timeout=10.0,
            )
        return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"SKILLS: list error: {e}")
        return []


async def get_skill(user_id: str, skill_id: str) -> dict | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/jarvis_skills",
                headers=_read_headers(),
                params={"select": "*", "user_id": f"eq.{user_id}", "id": f"eq.{skill_id}", "limit": "1"},
                timeout=10.0,
            )
        rows = resp.json() if resp.status_code == 200 else []
        return rows[0] if rows else None
    except Exception as e:
        print(f"SKILLS: get error: {e}")
        return None


async def update_skill(user_id: str, skill_id: str, fields: dict) -> dict | None:
    """Update editable fields. If full_content changes, re-chunk + re-embed."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    allowed = {"name", "description", "skill_type", "full_content", "operating_instructions", "enabled"}
    payload = {k: v for k, v in fields.items() if k in allowed}
    if "skill_type" in payload and payload["skill_type"] not in VALID_TYPES:
        payload.pop("skill_type")
    if not payload:
        return await get_skill(user_id, skill_id)
    payload["updated_at"] = "now()"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/jarvis_skills",
                headers=_write_headers(),
                params={"id": f"eq.{skill_id}", "user_id": f"eq.{user_id}"},
                json=payload,
                timeout=15.0,
            )
        updated = resp.json()[0] if resp.status_code in (200, 201) and resp.json() else None
    except Exception as e:
        print(f"SKILLS: update error: {e}")
        return None

    # Content changed → refresh the embedded chunks for this skill.
    if updated and "full_content" in payload:
        await _delete_skill_chunks(user_id, skill_id)
        stype = updated.get("skill_type", "knowledge")
        if stype in ("knowledge", "both"):
            await _embed_skill_chunks(user_id, skill_id, (payload["full_content"] or "").strip())
    return updated


async def _delete_skill_chunks(user_id: str, skill_id: str) -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.delete(
                f"{SUPABASE_URL}/rest/v1/document_chunks",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                params={"skill_id": f"eq.{skill_id}", "user_id": f"eq.{user_id}"},
                timeout=15.0,
            )
    except Exception as e:
        print(f"SKILLS: delete chunks error: {e}")


async def delete_skill(user_id: str, skill_id: str) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    await _delete_skill_chunks(user_id, skill_id)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{SUPABASE_URL}/rest/v1/jarvis_skills",
                headers={**_write_headers(), "Prefer": "return=minimal"},
                params={"id": f"eq.{skill_id}", "user_id": f"eq.{user_id}"},
                timeout=10.0,
            )
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"SKILLS: delete error: {e}")
        return False


async def set_enabled(user_id: str, skill_id: str, enabled: bool) -> dict | None:
    return await update_skill(user_id, skill_id, {"enabled": enabled})


# ── Phase 2: per-turn retrieval + injection ───────────────────────────────────

async def retrieve_knowledge_chunks(user_id: str, query: str, top_k: int = 6) -> list[dict]:
    """Embed the query and pull the most relevant skill-knowledge chunks via pgvector
    (match_skill_chunks). Best-effort: returns [] if there's no embedding backend or on
    any error — a chat turn must never fail because of skills."""
    if not SUPABASE_URL or not SUPABASE_KEY or not (query or "").strip():
        return []
    try:
        from backend.routes.documents import _embed
    except Exception:
        return []
    try:
        embeddings = await _embed([query])
        if not embeddings:
            return []
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/match_skill_chunks",
                headers=_write_headers(),
                json={"p_user_id": user_id, "p_embedding": embeddings[0], "p_top_k": top_k},
                timeout=15.0,
            )
        if resp.status_code == 200:
            return resp.json() or []
        print(f"SKILLS: retrieve rpc {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"SKILLS: retrieve error: {e}")
    return []


def _knowledge_block_from(chunks: list[dict], name_by_id: dict, min_similarity: float = 0.25) -> str:
    """Pure formatter (unit-tested): build the grounded knowledge block from retrieved
    chunks, keeping only chunks that belong to an ENABLED knowledge skill and clear the
    relevance threshold. Empty string when nothing qualifies."""
    relevant = [
        c for c in chunks
        if c.get("skill_id") in name_by_id and (c.get("similarity") or 0) >= min_similarity
    ]
    if not relevant:
        return ""
    lines = [
        "## RELEVANT KNOWLEDGE (from the user's own Skills)",
        "Ground your answer in the material below and cite the skill by name. Do NOT "
        "invent details beyond it; if it doesn't cover something, say so.",
    ]
    for c in relevant[:6]:
        name = name_by_id.get(c["skill_id"], "skill")
        lines.append(f"\n[Skill: {name}]\n{(c.get('content') or '').strip()}")
    return "\n".join(lines)


def _behavior_block_from(behavior_skills: list[dict]) -> str:
    """Pure formatter (unit-tested): build the always-on operating-rules block from the
    user's enabled behavior skills."""
    items = [s for s in behavior_skills if (s.get("operating_instructions") or "").strip()]
    if not items:
        return ""
    lines = [
        "## YOUR OPERATING SKILLS (user-authored — follow these every relevant turn)",
    ]
    for s in items[:12]:
        lines.append(f"- {s.get('name', 'Skill')}: {s['operating_instructions'].strip()}")
    return "\n".join(lines)


async def build_skill_prompt_block(user_id: str, user_message: str) -> str:
    """Assemble the per-turn skills injection: always-on behavior operating-rules +
    progressively-disclosed knowledge chunks relevant to this message. Never raises."""
    try:
        skills = await list_skills(user_id)
    except Exception:
        return ""
    enabled = [s for s in skills if s.get("enabled", True)]
    if not enabled:
        return ""

    behavior = [s for s in enabled if s.get("skill_type") in ("behavior", "both")]
    knowledge = {s["id"]: s.get("name", "skill") for s in enabled if s.get("skill_type") in ("knowledge", "both")}

    parts = []
    behavior_block = _behavior_block_from(behavior)
    if behavior_block:
        parts.append(behavior_block)

    if knowledge:
        chunks = await retrieve_knowledge_chunks(user_id, user_message)
        kb = _knowledge_block_from(chunks, knowledge)
        if kb:
            parts.append(kb)

    return "\n\n".join(parts)
