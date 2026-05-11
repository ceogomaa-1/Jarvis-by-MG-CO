from pydantic import BaseModel


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    user_id: str
    message: str
    conversation_history: list[Message]


class ChatResponse(BaseModel):
    response: str
    user_id: str
