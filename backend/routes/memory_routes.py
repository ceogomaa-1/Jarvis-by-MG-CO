from fastapi import APIRouter
from backend.memory import get_all_memories

router = APIRouter()


@router.get("/memory/{user_id}")
async def get_user_memories(user_id: str):
    memories = await get_all_memories(user_id)
    return {
        "user_id": user_id,
        "count": len(memories),
        "memories": memories,
    }
