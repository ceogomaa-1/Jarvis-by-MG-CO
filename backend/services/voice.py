import asyncio
import os
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

async def stream_jarvis_voice(text: str, voice_id: str | None = None):
    """Stream raw PCM float32 LE audio at 22050 Hz via Cartesia WebSocket.
    Yields bytes chunks as they arrive — first chunk typically in ~200ms."""
    vid = voice_id or JARVIS_VOICE_ID
    t0 = time.time()
    print(f"VOICE_WS_START: {len(text)} chars voice_id={vid}")

    client = _get_async_cartesia()
    ws = await client.tts.websocket()
    chunk_count = 0
    first_chunk_ms = None
    try:
        output_generate = await ws.send(
            model_id="sonic-2",
            transcript=text,
            voice={"mode": "id", "id": vid},
            output_format={
                "container": "raw",
                "encoding": "pcm_f32le",
                "sample_rate": 22050,
            },
            stream=True,
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

async def synthesize_jarvis_voice(text: str, voice_id: str | None = None) -> bytes:
    """Synthesize speech via Cartesia Sonic. Returns raw MP3 bytes."""
    vid = voice_id or JARVIS_VOICE_ID
    print(f"VOICE_SYNTH: synthesizing {len(text)} chars voice_id={vid}")

    client = _get_cartesia()

    def _synth():
        audio_bytes = b""
        for chunk in client.tts.bytes(
            model_id="sonic-2",
            transcript=text,
            voice={"mode": "id", "id": vid},
            language="en",
            output_format={
                "container": "mp3",
                "sample_rate": 44100,
                "bit_rate": 128000,
            },
        ):
            audio_bytes += chunk
        return audio_bytes

    audio_bytes = await asyncio.to_thread(_synth)
    cost_usd = len(text) * 0.000065
    print(f"VOICE_COST: chars={len(text)} cost=${cost_usd:.4f} bytes={len(audio_bytes)}")
    if not audio_bytes:
        raise RuntimeError("Cartesia returned empty audio")
    return audio_bytes
