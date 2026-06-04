"""
ElevenLabs voice connector. Uses httpx against the ElevenLabs REST API.
Test validates the API key by fetching the user profile.
Actions: list_voices, text_to_speech, list_agents, get_agent,
         create_agent, update_agent, delete_agent.
"""
import base64
import httpx

from backend.lib.business.connectors.base import BaseConnector, ConnectorResult

BASE = "https://api.elevenlabs.io/v1"
CONVAI = f"{BASE}/convai/agents"


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

    def _json_headers(self) -> dict:
        return {**self._headers(), "Content-Type": "application/json"}

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
                    headers=self._json_headers(),
                    json={"text": text, "model_id": "eleven_monolingual_v1"},
                    timeout=30.0,
                )
            resp.raise_for_status()
            audio_b64 = base64.b64encode(resp.content).decode()
            return ConnectorResult(ok=True, data={"audio_base64": audio_b64, "content_type": "audio/mpeg"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"TTS failed: {e}")

    # ── Conversational AI Agents ──────────────────────────────────────────────

    async def list_agents(self) -> ConnectorResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(CONVAI, headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            agents = [
                {
                    "agent_id": a.get("agent_id"),
                    "name": a.get("name"),
                    "voice_id": a.get("conversation_config", {}).get("tts", {}).get("voice_id"),
                    "metadata": a.get("metadata", {}),
                }
                for a in resp.json().get("agents", [])
            ]
            return ConnectorResult(ok=True, data={"agents": agents, "count": len(agents)})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"List agents failed: {e}")

    async def get_agent(self, agent_id: str) -> ConnectorResult:
        if not agent_id:
            return ConnectorResult(ok=False, error="`agent_id` is required")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{CONVAI}/{agent_id}", headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data=resp.json())
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Get agent failed: {e}")

    async def create_agent(
        self,
        name: str,
        system_prompt: str,
        first_message: str = "Hello! How can I help you?",
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        language: str = "en",
    ) -> ConnectorResult:
        if not name or not system_prompt:
            return ConnectorResult(ok=False, error="`name` and `system_prompt` are required")
        body = {
            "name": name,
            "conversation_config": {
                "agent": {
                    "prompt": {"prompt": system_prompt},
                    "first_message": first_message,
                    "language": language,
                },
                "tts": {"voice_id": voice_id},
            },
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{CONVAI}/create", headers=self._json_headers(), json=body, timeout=30.0)
            resp.raise_for_status()
            result = resp.json()
            return ConnectorResult(ok=True, data={
                "agent_id": result.get("agent_id"),
                "name": name,
                "status": "created",
                "message": f"Agent '{name}' created successfully. Review before publishing.",
            })
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Create agent failed: {e}")

    async def update_agent(self, agent_id: str, **kwargs) -> ConnectorResult:
        if not agent_id:
            return ConnectorResult(ok=False, error="`agent_id` is required")
        update_body: dict = {}
        if "name" in kwargs:
            update_body["name"] = kwargs["name"]
        if "system_prompt" in kwargs:
            (update_body
             .setdefault("conversation_config", {})
             .setdefault("agent", {})
             .setdefault("prompt", {}))["prompt"] = kwargs["system_prompt"]
        if "first_message" in kwargs:
            update_body.setdefault("conversation_config", {}).setdefault("agent", {})["first_message"] = kwargs["first_message"]
        if "voice_id" in kwargs:
            update_body.setdefault("conversation_config", {}).setdefault("tts", {})["voice_id"] = kwargs["voice_id"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    f"{CONVAI}/{agent_id}", headers=self._json_headers(), json=update_body, timeout=30.0
                )
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"agent_id": agent_id, "status": "updated"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Update agent failed: {e}")

    async def delete_agent(self, agent_id: str) -> ConnectorResult:
        if not agent_id:
            return ConnectorResult(ok=False, error="`agent_id` is required")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(f"{CONVAI}/{agent_id}", headers=self._headers(), timeout=15.0)
            resp.raise_for_status()
            return ConnectorResult(ok=True, data={"agent_id": agent_id, "status": "deleted"})
        except Exception as e:
            return ConnectorResult(ok=False, error=f"Delete agent failed: {e}")
