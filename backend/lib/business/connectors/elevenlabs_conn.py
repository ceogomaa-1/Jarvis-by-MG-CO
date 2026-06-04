"""
ElevenLabs voice connector. Uses httpx against the ElevenLabs REST API.
Test validates the API key by fetching the user profile.
Actions: list_voices, text_to_speech.
"""
import base64
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsConnector(BaseConnector):
    CONNECTOR_TYPE = "elevenlabs"
    DISPLAY_NAME = "ElevenLabs"
    DESCRIPTION = "Generate AI voice audio, clone voices, and manage your voice library."
    DOCS_URL = "https://elevenlabs.io/app/settings/api-keys"
    REQUIRED_FIELDS = {
        "api_key": {
            "label": "API Key",
            "type": "password",
            "placeholder": "your-elevenlabs-api-key",
            "secret": True,
            "required": True,
        },
    }

    def _headers(self) -> dict:
        return {"xi-api-key": self.credentials.get("api_key", "").strip()}

    async def test(self) -> ConnectorResult:
        missing = self._missing_fields()
        if missing:
            return ConnectorResult(ok=False, error=f"Missing required fields: {', '.join(missing)}")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/user", headers=self._headers(), timeout=10.0)
            if resp.status_code == 401:
                return ConnectorResult(ok=False, error="Invalid API key — find yours at elevenlabs.io/app/settings/api-keys.")
            resp.raise_for_status()
            sub = resp.json().get("subscription", {})
            used = sub.get("character_count", 0)
            limit = sub.get("character_limit", 0)
            return ConnectorResult(ok=True, data={"characters_used": used, "character_limit": limit})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"ElevenLabs connection failed: {e}")

    async def list_voices(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{BASE}/voices", headers=self._headers(), timeout=10.0)
            resp.raise_for_status()
            voices = [
                {"name": v["name"], "id": v["voice_id"], "category": v.get("category", "")}
                for v in resp.json().get("voices", [])
            ]
            return ConnectorResult(ok=True, data={"voices": voices})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List voices failed: {e}")

    async def text_to_speech(self, text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> ConnectorResult:
        """Convert text to speech. Returns audio as base64 MP3."""
        if not text:
            return ConnectorResult(ok=False, error="`text` is required")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{BASE}/text-to-speech/{voice_id}",
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json={"text": text, "model_id": "eleven_monolingual_v1"},
                    timeout=30.0,
                )
            resp.raise_for_status()
            audio_b64 = base64.b64encode(resp.content).decode()
            return ConnectorResult(ok=True, data={"audio_base64": audio_b64, "content_type": "audio/mpeg"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"TTS failed: {e}")
