import asyncio
import os
import time
from collections import defaultdict

# ─── Cartesia client (lazy-init so import doesn't fail if SDK missing) ─────────

_cartesia = None

def _get_cartesia():
    global _cartesia
    if _cartesia is None:
        from cartesia import Cartesia  # type: ignore
        _cartesia = Cartesia(api_key=os.getenv("CARTESIA_API_KEY", ""))
    return _cartesia


# ─── Voice identity ───────────────────────────────────────────────────────────
# Set JARVIS_VOICE_ID to whichever Cartesia voice ID sounds best.
# Audition via GET /api/voice/test?voice_id=<id>&text=Hey+what%27s+up
# List all options via GET /api/voice/list-voices

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


# ─── Core synthesis ───────────────────────────────────────────────────────────

async def synthesize_jarvis_voice(text: str, voice_id: str | None = None) -> bytes:
    """Synthesize speech via Cartesia Sonic. Returns raw MP3 bytes."""
    vid = voice_id or JARVIS_VOICE_ID
    print(f"VOICE_SYNTH: synthesizing {len(text)} chars voice_id={vid}")

    client = _get_cartesia()

    # Cartesia SDK is sync — run in thread to keep FastAPI non-blocking
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
