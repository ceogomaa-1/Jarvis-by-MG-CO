import os
import time
from collections import defaultdict

# ─── Voice identity — swap these constants to change Jarvis's voice ──────────
# context = reference clips that give CSM 1B the voice character to clone.
# The model matches timber, pace, and energy from these clips.

JARVIS_VOICE_REF_A = {
    "audio_url": "https://huggingface.co/spaces/sesame/csm-1b/resolve/main/prompts/conversational_a.wav",
    "speaker_id": 0,
    "prompt": (
        "like revising for an exam I'd have to try and like keep up the momentum because I'd "
        "start really early I'd be like okay I'm gonna start revising now and then like you're "
        "revising for ages and then I just like start losing steam I didn't do that for the exam "
        "we had recently to be fair that was a more of a last minute scenario but like yeah I'm "
        "trying to like yeah I noticed this yesterday that like Mondays I sort of start the day "
        "with this not like a panic but like a"
    ),
}

JARVIS_VOICE_REF_B = {
    "audio_url": "https://huggingface.co/spaces/sesame/csm-1b/resolve/main/prompts/conversational_b.wav",
    "speaker_id": 0,
    "prompt": (
        "I don't know, I think it's just like, when you have a lot going on it's hard to know "
        "where to start. Like there's this thing where you want to do everything perfectly but "
        "then you end up doing nothing because you're so worried about getting it wrong. I've been "
        "trying to just pick one thing and do that, and then move on. It's been actually helping "
        "a lot more than I thought it would."
    ),
}

# Active reference — flip to JARVIS_VOICE_REF_B after testing via /api/voice/test
JARVIS_VOICE_REF = JARVIS_VOICE_REF_A

# ─── In-memory rate limiting ──────────────────────────────────────────────────

_rl: dict[str, dict] = defaultdict(lambda: {"count": 0, "window_start": 0.0})
_MAX_REQUESTS_PER_HOUR = 100
_MAX_CHARS_PER_REQUEST = 1000


def check_rate_limit(user_id: str, char_count: int) -> str | None:
    """Return error string if over limit, None if OK. Mutates counter on pass."""
    now = time.time()
    state = _rl[user_id]
    if now - state["window_start"] > 3600:
        state["count"] = 0
        state["window_start"] = now
    if char_count > _MAX_CHARS_PER_REQUEST:
        return f"Text too long — {char_count} chars exceeds {_MAX_CHARS_PER_REQUEST} char limit per request"
    if state["count"] >= _MAX_REQUESTS_PER_HOUR:
        return f"Voice rate limit: {_MAX_REQUESTS_PER_HOUR} requests/hour exceeded"
    state["count"] += 1
    return None


# ─── Core synthesis function ──────────────────────────────────────────────────

async def synthesize_jarvis_voice(text: str, voice_ref: dict | None = None) -> str:
    """Call Fal.ai CSM 1B with scene + context. Returns public audio URL."""
    import fal_client  # type: ignore

    api_key = os.getenv("FAL_API_KEY")
    if not api_key:
        raise RuntimeError("FAL_API_KEY not set")
    os.environ.setdefault("FAL_KEY", api_key)

    ref = voice_ref or JARVIS_VOICE_REF

    result = await fal_client.subscribe_async(
        "fal-ai/csm-1b",
        arguments={
            "scene": [{"text": text, "speaker_id": 0}],
            "context": [ref],
        },
    )

    audio_url = result.get("audio", {}).get("url", "")
    cost = len(text) * 0.00003
    print(f"VOICE_COST: chars={len(text)} cost=${cost:.4f} url={'yes' if audio_url else 'MISSING'}")
    if not audio_url:
        raise RuntimeError(f"Fal returned no audio URL — raw: {result}")
    return audio_url
