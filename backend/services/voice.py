import asyncio
import os
import re
import time
from collections import defaultdict

# ─── Cartesia clients (lazy-init) ─────────────────────────────────────────────

_cartesia = None
_async_cartesia = None


def _get_cartesia():
    global _cartesia
    if _cartesia is None:
        from cartesia import Cartesia  # type: ignore
        _cartesia = Cartesia(api_key=os.getenv("CARTESIA_API_KEY", ""))
    return _cartesia


def _get_async_cartesia():
    global _async_cartesia
    if _async_cartesia is None:
        from cartesia import AsyncCartesia  # type: ignore
        _async_cartesia = AsyncCartesia(api_key=os.getenv("CARTESIA_API_KEY", ""))
    return _async_cartesia


# ─── Voice identity ───────────────────────────────────────────────────────────

JARVIS_VOICE_ID = os.getenv("JARVIS_VOICE_ID", "a0e99841-438c-4a64-b679-ae501e7d6091")

# Model stays on sonic-2 (current production sound) until this is deliberately
# flipped. Live-verified: sonic-3 accepts JARVIS_VOICE_ID with no error, but its
# baseline output differs from sonic-2's for identical text/voice_id — audition
# via /voice/test?model_id=sonic-3 before ever changing this default.
CARTESIA_MODEL_ID = os.getenv("CARTESIA_MODEL_ID", "sonic-2")

# ─── Expression controls (speed / emotion / volume) ──────────────────────────
# Cartesia's `generation_config` (emotion/speed/volume) only has an effect on
# sonic-3+ models — confirmed live, it's a silent no-op on sonic-2. The legacy
# top-level `speed` enum is model-agnostic but "experimental, may not work for
# all voices" per Cartesia's own SDK docs — confirmed live it's a no-op for
# JARVIS_VOICE_ID specifically. Both are wired through regardless so they
# activate automatically the moment CARTESIA_MODEL_ID is set to a sonic-3 model.

_SONIC3_SPEED_FLOAT = {"slow": 0.85, "normal": 1.0, "fast": 1.2}


def _is_sonic3(model_id: str) -> bool:
    return model_id.startswith("sonic-3")


def _build_voice_kwargs(
    model_id: str,
    speed: str | None,
    emotion: str | None,
    volume: float | None,
) -> dict:
    """Returns the extra kwargs (speed / generation_config) to merge into a
    Cartesia TTS call, given the resolved model. Empty dict when nothing to add."""
    extra: dict = {}
    if _is_sonic3(model_id):
        gen_cfg: dict = {}
        if emotion:
            gen_cfg["emotion"] = emotion
        if speed in _SONIC3_SPEED_FLOAT:
            gen_cfg["speed"] = _SONIC3_SPEED_FLOAT[speed]
        if volume is not None:
            gen_cfg["volume"] = volume
        if gen_cfg:
            extra["generation_config"] = gen_cfg
    elif speed in ("slow", "normal", "fast"):
        extra["speed"] = speed
    return extra


# Priority-ordered keyword/punctuation heuristic — cheap, deterministic, no LLM
# call. Scans the outgoing reply text (not the user's message) since that's
# what's about to be spoken. First matching emotion wins.
_EMOTION_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(sleep|sleepy|drift off|close your eyes|wind down|get some rest|take it easy|breathe|relax(ed|ing)?|unwind)\b", re.I), "calm"),
    (re.compile(r"\b(sorry|that sucks|rough day|hard time|tough break|that'?s awful|i know that hurts)\b", re.I), "sympathetic"),
    (re.compile(r"\b(haha|lmao|lol|hehe|ha-{1,2})\b", re.I), "happy"),
    (re.compile(r"\b(babe|ya albi|ya 3omri|handsome|gorgeous)\b", re.I), "flirtatious"),
    (re.compile(r"\b(let'?s go|hell yes|fuck yes|that'?s huge|insane|incredible|amazing|yo{1,2})\b", re.I), "excited"),
    (re.compile(r"\b(i'?m proud|nice work|well done|killing it)\b", re.I), "proud"),
    (re.compile(r"\b(wonder|curious|what if|why|how come)\b", re.I), "curious"),
]


def derive_expression(text: str) -> tuple[str | None, str | None]:
    """Cheap heuristic scan of outgoing reply text -> (speed_label, emotion).
    Pure and deterministic, no I/O. Returns (None, None) for neutral text,
    which means "don't touch anything" downstream."""
    if not text:
        return None, None

    emotion = None
    for pattern, label in _EMOTION_RULES:
        if pattern.search(text):
            emotion = label
            break

    bang_count = text.count("!")
    speed = None
    if bang_count >= 2 or emotion == "excited":
        speed = "fast"
    elif "..." in text or emotion in ("sympathetic", "calm"):
        speed = "slow"

    return speed, emotion


# ─── In-memory rate limiting ──────────────────────────────────────────────────

_rl: dict[str, dict] = defaultdict(lambda: {"count": 0, "window_start": 0.0})
_MAX_REQUESTS_PER_HOUR = 100
_MAX_CHARS_PER_REQUEST = 1500


def check_rate_limit(user_id: str, char_count: int) -> str | None:
    """Return error string if over limit, None if OK. Mutates counter on pass."""
    now = time.time()
    state = _rl[user_id]
    if now - state["window_start"] > 3600:
        state["count"] = 0
        state["window_start"] = now
    if char_count > _MAX_CHARS_PER_REQUEST:
        return f"Text too long — {char_count} chars exceeds {_MAX_CHARS_PER_REQUEST} char limit"
    if state["count"] >= _MAX_REQUESTS_PER_HOUR:
        return f"Voice rate limit: {_MAX_REQUESTS_PER_HOUR} requests/hour exceeded"
    state["count"] += 1
    return None


# ─── Streaming synthesis (WebSocket — ~200ms first chunk) ────────────────────

async def stream_jarvis_voice(
    text: str,
    voice_id: str | None = None,
    speed: str | None = None,
    emotion: str | None = None,
    volume: float | None = None,
    model_id: str | None = None,
):
    """Stream raw PCM float32 LE audio at 22050 Hz via Cartesia WebSocket.
    Yields bytes chunks as they arrive — first chunk typically in ~200ms.

    speed: "slow" | "normal" | "fast" (optional).
    emotion: a Cartesia sonic-3 emotion label, e.g. "excited", "curious", "sad" (optional).
    volume: 0.5-2.0, sonic-3 only (optional).
    model_id: overrides CARTESIA_MODEL_ID for this call (optional, mainly for auditioning)."""
    vid = voice_id or JARVIS_VOICE_ID
    mid = model_id or CARTESIA_MODEL_ID
    t0 = time.time()
    print(f"VOICE_WS_START: {len(text)} chars voice_id={vid} model_id={mid} speed={speed} emotion={emotion}")

    client = _get_async_cartesia()
    ws = await client.tts.websocket()
    chunk_count = 0
    first_chunk_ms = None
    try:
        output_generate = await ws.send(
            model_id=mid,
            transcript=text,
            voice={"mode": "id", "id": vid},
            output_format={
                "container": "raw",
                "encoding": "pcm_f32le",
                "sample_rate": 22050,
            },
            stream=True,
            **_build_voice_kwargs(mid, speed, emotion, volume),
        )
        async for chunk in output_generate:
            # SDK may return object with .audio or dict with "audio"
            audio = chunk.audio if hasattr(chunk, "audio") else chunk.get("audio", b"")
            if audio:
                if chunk_count == 0:
                    first_chunk_ms = int((time.time() - t0) * 1000)
                    print(f"VOICE_WS_FIRST_CHUNK: {first_chunk_ms}ms")
                chunk_count += 1
                yield audio
    finally:
        await ws.close()

    total_ms = int((time.time() - t0) * 1000)
    cost_usd = len(text) * 0.000065
    print(f"VOICE_WS_END: chunks={chunk_count} total={total_ms}ms first={first_chunk_ms}ms cost=${cost_usd:.4f}")


# ─── Non-streaming fallback (for /voice/test and backward compat) ─────────────

async def synthesize_jarvis_voice(
    text: str,
    voice_id: str | None = None,
    speed: str | None = None,
    emotion: str | None = None,
    volume: float | None = None,
    model_id: str | None = None,
) -> bytes:
    """Synthesize speech via Cartesia Sonic. Returns raw MP3 bytes.

    speed: "slow" | "normal" | "fast" (optional).
    emotion: a Cartesia sonic-3 emotion label, e.g. "excited", "curious", "sad" (optional).
    volume: 0.5-2.0, sonic-3 only (optional).
    model_id: overrides CARTESIA_MODEL_ID for this call (optional, mainly for auditioning)."""
    vid = voice_id or JARVIS_VOICE_ID
    mid = model_id or CARTESIA_MODEL_ID
    print(f"VOICE_SYNTH: synthesizing {len(text)} chars voice_id={vid} model_id={mid} speed={speed} emotion={emotion}")

    client = _get_cartesia()

    def _synth():
        audio_bytes = b""
        for chunk in client.tts.bytes(
            model_id=mid,
            transcript=text,
            voice={"mode": "id", "id": vid},
            language="en",
            output_format={
                "container": "mp3",
                "sample_rate": 44100,
                "bit_rate": 128000,
            },
            **_build_voice_kwargs(mid, speed, emotion, volume),
        ):
            audio_bytes += chunk
        return audio_bytes

    audio_bytes = await asyncio.to_thread(_synth)
    cost_usd = len(text) * 0.000065
    print(f"VOICE_COST: chars={len(text)} cost=${cost_usd:.4f} bytes={len(audio_bytes)}")
    if not audio_bytes:
        raise RuntimeError("Cartesia returned empty audio")
    return audio_bytes
