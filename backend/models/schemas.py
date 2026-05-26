from typing import Any
from pydantic import BaseModel, field_validator


class Message(BaseModel):
    role: str
    content: Any  # accept object content from frontend; coerced to str below

    @field_validator("content", mode="before")
    @classmethod
    def coerce_content(cls, v):
        if isinstance(v, str):
            return v
        if v is None:
            return ""
        import json
        try:
            return json.dumps(v)
        except Exception:
            return str(v)


class ChatRequest(BaseModel):
    user_id: str
    message: str
    conversation_history: list[Message] = []
    image_base64: str | None = None
    image_type: str | None = None
    attachments: list[dict] = []  # [{url, file_type, file_id}] — future URL-based attachment flow
    voice_mode: bool = False  # True → inject voice system prompt, TTS response on frontend


class ChatResponse(BaseModel):
    response: str
    user_id: str
    _debug: str | None = None
