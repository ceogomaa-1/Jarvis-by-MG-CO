"""
Dump Learn — the reasoning/explain engine (Jarvis Personal, Study Mode).

Turns a bin's already-condensed material (from dump_learn_ingest) into one
structured lesson: TL;DR, concept sections, an optional mind map, and a short
self-check quiz — all from a SINGLE model call per (bin, level), not three
separate ones.

Three comprehension levels (Child / Graduate / Expert) all use the same model
(Sonnet 5 — see model_router.SONNET; no Sonnet 4.6, no Opus) so the difference
is real without pinning two levels to an older/deprecated model. What actually
changes between levels:
  - context depth   — Child/Graduate read each item's condensed skeleton;
                       Expert reads a much larger slice of the raw extracted
                       text directly (reasoning over primary source, not just
                       a summary of it).
  - output budget    — Expert gets a materially higher max_tokens ceiling and
                       is asked for edge cases/caveats/comparative depth.
  - prompt rigor     — three distinct system prompts control vocabulary
                       ceiling, analogy density, and structural strictness.

Every generated lesson is cached in dump_learn_explanations keyed on
(bin_id, level, source_fingerprint) — re-picking an already-seen level, or
reopening a bin, is a free read. The fingerprint changes the moment the bin's
ready items change, so a stale lesson can never be served after new material
is added.
"""
from __future__ import annotations

import hashlib
import json
import os

import httpx

from backend.lib.business.cost import UsageAccumulator
from backend.lib.business.model_router import SONNET

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

EXPLANATIONS_TABLE = "dump_learn_explanations"

# How much of each item's material feeds the explain call, per level.
_GRADUATE_CHARS_PER_ITEM = 8_000
_EXPERT_CHARS_PER_ITEM = 20_000

_MAX_TOKENS = {"child": 2200, "graduate": 2800, "expert": 4500}

_RESPONSE_SCHEMA = """\
Respond with ONLY valid JSON (no markdown fences, no preamble), matching exactly:
{
  "tldr": "2-3 plain sentences capturing the big picture",
  "sections": [
    {
      "heading": "short section title",
      "body_md": "the explanation for this concept, in markdown",
      "callout_type": "analogy" | "nuance" | null,
      "callout_text": "a short callout to accompany the section, or null"
    }
  ],
  "mind_map": {
    "nodes": [{"id": "slug", "label": "Concept name", "weight": 0.0-1.0, "category": "short tag"}],
    "edges": [{"source": "slug", "target": "slug", "label": "relationship, short"}]
  } | null,
  "quiz": [{"question": "...", "answer": "..."}]
}
Only include "mind_map" when the material genuinely has multiple connected concepts worth \
mapping (4+ concepts with real relationships) — otherwise use null. Always include 3-5 quiz \
questions matched to the requested comprehension level."""

_LEVEL_PROMPTS = {
    "child": f"""\
You are Jarvis, explaining study material to a curious, sharp child (roughly age 8-11). This is \
NOT a diluted version of the adult explanation — it is a DIFFERENT explanation built for a \
different mind:
- Vocabulary ceiling: everyday words only. If a technical term is unavoidable, define it in the \
same breath using something the child already knows (a kitchen, a playground, a video game, \
animals, weather).
- Every section gets a concrete, vivid analogy — this is not optional flavor, it is the primary \
teaching tool. Prefer analogies to things a kid touches/sees daily.
- Short sentences. Short paragraphs. Warm, encouraging tone — never condescending, never scary.
- Keep total length modest: a few clear sections beat ten thin ones. Depth is sacrificed for \
clarity on purpose at this level.
- Quiz questions are simple recall/recognition, phrased playfully.

{_RESPONSE_SCHEMA}""",

    "graduate": f"""\
You are Jarvis, explaining study material the way a sharp, articulate classmate would — someone \
who understood the reading and can walk you through it clearly, assuming general education but \
no specialist background:
- Balanced vocabulary: technical terms are fine when they're the standard term for the thing, but \
each gets a one-line plain-English gloss on first use.
- Structure the material into clear, named sections that mirror how the source itself is \
organized. Use an analogy callout where it genuinely aids understanding, but don't force one into \
every section.
- Prioritize clarity and correct structure over exhaustive coverage of every minor detail.
- Quiz questions test real understanding of the core ideas, not just recall of a fact.

{_RESPONSE_SCHEMA}""",

    "expert": f"""\
You are Jarvis, explaining study material to someone who wants full technical/academic depth — \
treat them as a peer, not a student being protected from complexity:
- Use precise, field-standard terminology without diluting it. Do not define basic terms in the \
field; do define genuinely obscure or source-specific ones.
- Go beyond the surface reading: surface caveats, edge cases, ambiguities, internal \
contradictions in the source, and where relevant, how this compares to standard treatments of \
the topic. Use a "nuance" callout for exactly this purpose instead of an analogy callout.
- Reason directly over the raw source excerpts you're given, not just a summary of them — cite \
specifics (numbers, named claims, direct terms) from the material rather than paraphrasing them \
away.
- Depth over brevity here: it's fine, expected even, for sections to be substantive.
- Quiz questions should require applying the material or reasoning about an edge case, not just \
recalling a definition.

{_RESPONSE_SCHEMA}""",
}


def _read_headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def _write_headers(prefer: str = "return=representation") -> dict:
    return {**_read_headers(), "Content-Type": "application/json", "Prefer": prefer}


def fingerprint_items(items: list[dict]) -> str:
    """Changes the moment the bin's ready-item set (or its content) changes, so a
    stale cached explanation is never served after new/edited material lands."""
    parts = sorted(
        f"{it['id']}:{it.get('updated_at', '')}:{it.get('token_estimate', 0)}"
        for it in items
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _parse_json_response(raw: str) -> dict | None:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        raw = "\n".join(inner).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _fallback_lesson(raw_text: str) -> dict:
    """Never let a parse failure lose the model's work — surface it as one section
    rather than erroring out (same 'never silently drop' principle as jarvis_skills)."""
    return {
        "tldr": "",
        "sections": [{"heading": "Explanation", "body_md": raw_text, "callout_type": None, "callout_text": None}],
        "mind_map": None,
        "quiz": [],
    }


def _assemble_context(items: list[dict], level: str) -> str:
    per_item_cap = _EXPERT_CHARS_PER_ITEM if level == "expert" else _GRADUATE_CHARS_PER_ITEM
    parts = []
    for it in items:
        label = it.get("source_name") or "Source"
        if level == "expert":
            # Expert reasons over the primary text directly, not just the skeleton.
            body = it.get("extracted_text") or it.get("skeleton_md") or ""
        else:
            # Child/Graduate read the condensed version when one exists.
            body = it.get("skeleton_md") or it.get("extracted_text") or ""
        parts.append(f"### {label}\n{body[:per_item_cap]}")
    return "\n\n".join(parts)


async def _get_cached(bin_id: str, level: str, fp: str) -> dict | None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/{EXPLANATIONS_TABLE}",
                headers=_read_headers(),
                params={
                    "select": "*",
                    "bin_id": f"eq.{bin_id}",
                    "level": f"eq.{level}",
                    "source_fingerprint": f"eq.{fp}",
                    "limit": "1",
                },
                timeout=10.0,
            )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    except Exception as e:
        print(f"DUMP_LEARN: explanation cache read error: {e}")
    return None


async def _store_explanation(bin_id: str, user_id: str, level: str, fp: str, lesson: dict, model: str, cost_usd: float) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    payload = {
        "bin_id": bin_id, "user_id": user_id, "level": level, "source_fingerprint": fp,
        "tldr": lesson.get("tldr", ""),
        "sections_json": lesson.get("sections", []),
        "mind_map_json": lesson.get("mind_map"),
        "quiz_json": lesson.get("quiz", []),
        "model_used": model,
        "cost_usd": round(cost_usd, 5),
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/{EXPLANATIONS_TABLE}",
                headers=_write_headers("return=minimal"),
                json=payload,
                timeout=15.0,
            )
    except Exception as e:
        print(f"DUMP_LEARN: explanation cache write error: {e}")


async def explain_bin(bin_id: str, user_id: str, level: str, items: list[dict]) -> dict:
    """Returns {"lesson": {...}, "cached": bool, "cost": {...} | None}."""
    level = level if level in _LEVEL_PROMPTS else "graduate"
    ready = [it for it in items if it.get("status") == "ready" and it.get("extracted_text")]
    if not ready:
        return {"lesson": None, "cached": False, "cost": None, "error": "No material is ready to explain yet."}

    fp = fingerprint_items(ready)
    cached = await _get_cached(bin_id, level, fp)
    if cached:
        return {
            "lesson": {
                "tldr": cached.get("tldr", ""),
                "sections": cached.get("sections_json", []),
                "mind_map": cached.get("mind_map_json"),
                "quiz": cached.get("quiz_json", []),
            },
            "cached": True,
            "cost": None,
        }

    if not ANTHROPIC_API_KEY:
        return {"lesson": None, "cached": False, "cost": None, "error": "Explaining isn't configured on this deployment."}

    context = _assemble_context(ready, level)
    usage_acc = UsageAccumulator(SONNET)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": SONNET,
                    "max_tokens": _MAX_TOKENS.get(level, 2800),
                    "system": [{
                        "type": "text",
                        "text": _LEVEL_PROMPTS[level],
                        "cache_control": {"type": "ephemeral"},
                    }],
                    "messages": [{"role": "user", "content": f"MATERIAL TO EXPLAIN:\n\n{context}"}],
                },
                timeout=90.0,
            )
    except Exception as e:
        return {"lesson": None, "cached": False, "cost": None, "error": f"Explaining failed ({type(e).__name__})."}

    if resp.status_code != 200:
        print(f"DUMP_LEARN: explain API error {resp.status_code}: {resp.text[:300]}")
        return {"lesson": None, "cached": False, "cost": None, "error": "Explaining is temporarily unavailable."}

    data = resp.json()
    # Non-streaming Anthropic responses carry the FULL usage block already (input +
    # cache buckets + final output_tokens) — add_message_start intentionally skips
    # output_tokens (it's built for streaming's message_start event), so pair it with
    # one add_round_output call to get the complete, non-double-counted total.
    usage_acc.add_message_start(data.get("usage") or {})
    usage_acc.add_round_output((data.get("usage") or {}).get("output_tokens", 0))

    raw = data.get("content", [{}])[0].get("text", "").strip()
    lesson = _parse_json_response(raw) or _fallback_lesson(raw)
    lesson.setdefault("tldr", "")
    lesson.setdefault("sections", [])
    lesson.setdefault("mind_map", None)
    lesson.setdefault("quiz", [])

    cost = usage_acc.cost()
    await _store_explanation(bin_id, user_id, level, fp, lesson, SONNET, cost.get("total_usd", 0.0))
    print(usage_acc.log_line())
    return {"lesson": lesson, "cached": False, "cost": cost}


# ── Scoped follow-up chat (retrieval-backed when the bin has embeddings) ─────

_FOLLOWUP_SYSTEM = """\
You are Jarvis, continuing a study session about material the user already had explained to them \
at the "{level}" comprehension level. Answer their follow-up question grounded ONLY in the \
material below — if it isn't covered, say so plainly rather than guessing. Match the same \
comprehension level in your tone/depth as the original explanation."""


async def _retrieve_relevant_chunks(items: list[dict], question: str, top_k: int = 6) -> str:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return ""
    try:
        from backend.routes.documents import _embed
    except Exception:
        return ""
    embeddings = await _embed([question])
    if not embeddings:
        return ""
    q_embedding = embeddings[0]

    all_hits: list[dict] = []
    try:
        async with httpx.AsyncClient() as client:
            for it in items:
                resp = await client.post(
                    f"{SUPABASE_URL}/rest/v1/rpc/match_dump_learn_chunks",
                    headers=_write_headers("return=representation"),
                    json={"p_item_id": it["id"], "p_embedding": q_embedding, "p_top_k": top_k},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    all_hits.extend(resp.json())
    except Exception as e:
        print(f"DUMP_LEARN: retrieval error: {e}")
        return ""

    all_hits.sort(key=lambda h: h.get("similarity", 0), reverse=True)
    return "\n\n".join(h["content"] for h in all_hits[:top_k])


async def answer_followup(bin_id: str, user_id: str, level: str, items: list[dict], question: str) -> dict:
    """Returns {"answer": str, "cost": {...} | None, "error": str | None}."""
    ready = [it for it in items if it.get("status") == "ready" and it.get("extracted_text")]
    if not ready:
        return {"answer": "", "cost": None, "error": "There's no material in this bin yet."}
    if not ANTHROPIC_API_KEY:
        return {"answer": "", "cost": None, "error": "Chat isn't configured on this deployment."}

    retrieved = await _retrieve_relevant_chunks(ready, question)
    context = retrieved if retrieved else _assemble_context(ready, level)

    usage_acc = UsageAccumulator(SONNET)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": SONNET,
                    "max_tokens": 1200,
                    "system": _FOLLOWUP_SYSTEM.format(level=level),
                    "messages": [{
                        "role": "user",
                        "content": f"MATERIAL:\n{context}\n\nQUESTION: {question}",
                    }],
                },
                timeout=60.0,
            )
    except Exception as e:
        return {"answer": "", "cost": None, "error": f"That failed ({type(e).__name__})."}

    if resp.status_code != 200:
        return {"answer": "", "cost": None, "error": "That's temporarily unavailable."}

    data = resp.json()
    usage_acc.add_message_start(data.get("usage") or {})
    usage_acc.add_round_output((data.get("usage") or {}).get("output_tokens", 0))
    answer = data.get("content", [{}])[0].get("text", "").strip()
    return {"answer": answer, "cost": usage_acc.cost(), "error": None}
