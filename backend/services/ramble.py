"""Continuous-talk ("ramble") mode: Rue keeps generating + speaking without
waiting for another user turn, until barge-in cancels it or a safety limit
hits. Text generation only lives here — TTS delivery reuses the existing
stream_jarvis_voice()/synthesize-stream pipeline, called once per chunk by
the caller (see /voice/ramble/start in voice_routes.py).

Trigger phrase list is mirrored (not shared) in frontend/lib/jarvisVoice.js —
keep the two in sync if you add phrasings.
"""

import os
import re
import time

MAX_RAMBLE_SECONDS = int(os.getenv("RAMBLE_MAX_SECONDS", "300"))
MAX_RAMBLE_CHUNKS = int(os.getenv("RAMBLE_MAX_CHUNKS", "40"))

_RAMBLE_TONE = (
    "CONTINUOUS-TALK MODE: The user asked you to just keep talking without waiting "
    "for them to respond — they're not going to reply after this. Keep going "
    "naturally: continue the thread, riff on it, tell a related story, share a "
    "thought and follow it somewhere. Never repeat anything you already said in "
    "this ramble. Never ask a question that needs an answer to continue, and "
    "never say things like 'let me know if you want me to keep going' — just keep "
    "going. Short, natural, voice-friendly chunks, like a friend riffing out loud."
)
_CONTINUE_CUE = "(keep going — don't repeat yourself, no need to wait for me)"

_RAMBLE_INTENT_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"\bkeep (on )?talking\b",
        r"\bdon'?t (ever )?stop talking\b",
        r"\bkeep going\b",
        r"\bjust keep (talking|going|rambling|chatting)\b",
        r"\bdon'?t stop\b",
        r"\bkeep rambling\b",
        r"\bjust ramble\b",
        r"\btalk to me\b",
        r"\bsay more\b",
        r"\bkeep the conversation going\b",
        r"\bnever stop talking\b",
        r"\btired of (responding|replying|answering)\b",
        r"\bjust talk\b",
    ]
]


def detect_ramble_intent(text: str) -> bool:
    """Cheap, paraphrase-tolerant heuristic — no LLM call. True if the text
    plausibly asks Rue to enter continuous-talk mode."""
    if not text:
        return False
    return any(p.search(text) for p in _RAMBLE_INTENT_PATTERNS)


# ─── Per-user session state (in-memory — mirrors the rate-limit pattern in
# backend.services.voice) ──────────────────────────────────────────────────

_ramble_state: dict[str, dict] = {}


def start_ramble_session(user_id: str) -> None:
    existing = _ramble_state.get(user_id)
    if existing:
        # Orphan any lingering generator from a prior session for this user
        # (it holds a reference to this same dict object, not the new one).
        existing["cancel"] = True
    _ramble_state[user_id] = {"cancel": False, "started_at": time.time(), "chunks": 0}


def cancel_ramble(user_id: str) -> None:
    state = _ramble_state.get(user_id)
    if state:
        state["cancel"] = True


def _should_stop(state: dict) -> bool:
    if state["cancel"]:
        return True
    if state["chunks"] >= MAX_RAMBLE_CHUNKS:
        return True
    if time.time() - state["started_at"] >= MAX_RAMBLE_SECONDS:
        return True
    return False


async def ramble_chunks(
    user_id: str,
    seed_text: str,
    conversation_history: list,
    memory_context: str,
    user_model_context: str,
    live_context: str,
):
    """Yields successive text chunks for continuous-talk mode. Caller is
    responsible for TTS + delivery of each chunk (reuse the normal TTS path —
    don't build a second one). Stops on cancellation, max chunk count, or max
    duration, whichever comes first. Ramble turns are NOT persisted to
    conversation history/memory — this is a transient monologue, not a real
    exchange the user is party to."""
    from backend.llm import jarvis_think

    start_ramble_session(user_id)
    state = _ramble_state[user_id]
    rolling_history = list(conversation_history[-6:])
    next_message = seed_text or "just keep talking"

    try:
        while not _should_stop(state):
            try:
                chunk = await jarvis_think(
                    user_message=next_message,
                    conversation_history=rolling_history,
                    memory_context=memory_context,
                    user_model_context=user_model_context,
                    tone_context=_RAMBLE_TONE,
                    available_tools=None,
                    user_id=user_id,
                    live_context=live_context,
                    voice_mode=True,
                )
            except Exception as e:
                print(f"RAMBLE_ERROR: user_id={user_id} -> {e}")
                break

            chunk = (chunk or "").strip()
            if not chunk:
                break

            rolling_history.append({"role": "user", "content": next_message})
            rolling_history.append({"role": "assistant", "content": chunk})
            rolling_history = rolling_history[-8:]

            state["chunks"] += 1
            yield chunk
            next_message = _CONTINUE_CUE
    finally:
        # Only clear if we still own the slot (a newer session may have replaced us).
        if _ramble_state.get(user_id) is state:
            _ramble_state.pop(user_id, None)
