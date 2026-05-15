from fastapi import APIRouter
from backend.conversation import get_conversation_history

router = APIRouter()


@router.get("/history/{user_id}")
async def get_history(user_id: str):
    messages = await get_conversation_history(user_id, limit=20)
    return {"messages": messages}
