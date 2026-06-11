"""
OpenAI text-embedding-3-small wrapper for Mind memory embeddings.
"""
import os

from openai import AsyncOpenAI

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI | None:
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def embed_text(text: str) -> list[float] | None:
    """Embed a memory string. Returns None if OpenAI isn't configured or the call fails."""
    client = _get_client()
    if not client or not text or not text.strip():
        return None
    try:
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
        return resp.data[0].embedding
    except Exception as e:
        print(f"MIND_EMBED: error: {e}")
        return None
