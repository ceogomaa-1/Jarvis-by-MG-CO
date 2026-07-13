"""Message feedback — the 👍/👎 under every Rue reply (Personal).

POST /api/feedback/message stores the rating in the rater's own user model and
distills it into per-user style lessons (backend.lib.personal.feedback_trainer).
Strictly per-user: feedback only ever trains the Rue of the account that sent it.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib.personal.feedback_trainer import record_feedback

router = APIRouter()


class MessageFeedback(BaseModel):
    user_id: str
    rating: str              # 'up' | 'down'
    message_text: str        # the assistant reply being rated
    user_prompt: str = ""    # the user message that reply answered (context)
    comment: str = ""        # optional "tell Rue why" note


@router.post("/feedback/message")
async def message_feedback(req: MessageFeedback):
    user_id = (req.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    if not (req.message_text or "").strip():
        raise HTTPException(status_code=400, detail="message_text is required")

    result = await record_feedback(
        user_id=user_id,
        rating=req.rating,
        message_text=req.message_text,
        user_prompt=req.user_prompt,
        comment=req.comment,
    )
    return result
