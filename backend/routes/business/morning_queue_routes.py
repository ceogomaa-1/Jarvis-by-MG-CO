"""
Morning Queue routes.

  POST   /business/morning-queue/generate-all   — secret-header protected, for Render Cron
  POST   /business/morning-queue/generate-one   — manual single-user trigger (testing)
  GET    /business/morning-queue                — today + yesterday items for a user
  GET    /business/morning-queue/unread-count   — badge count
  PATCH  /business/morning-queue/read-all       — mark today+yesterday read (modal opened)
  POST   /business/morning-queue/{item_id}/act  — mark read, bury memory, return action_prompt
"""
import os

from fastapi import APIRouter, Header, HTTPException

from backend.lib.business import morning_queue as mq

router = APIRouter()

CRON_SECRET = os.getenv("MORNING_QUEUE_CRON_SECRET", "")


@router.post("/business/morning-queue/generate-all")
async def generate_all(x_cron_secret: str = Header(default="")):
    if not CRON_SECRET or x_cron_secret != CRON_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")
    return await mq.generate_for_all_users()


@router.post("/business/morning-queue/generate-one")
async def generate_one(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await mq.generate_queue_for_user(user_id, force=True)


@router.get("/business/morning-queue")
async def get_queue(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await mq.list_queue_items(user_id)


@router.get("/business/morning-queue/unread-count")
async def get_unread_count(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"unread": await mq.unread_count(user_id)}


@router.patch("/business/morning-queue/read-all")
async def read_all(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"ok": await mq.mark_all_read(user_id)}


@router.post("/business/morning-queue/{item_id}/act")
async def act_on_item(item_id: str, user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await mq.bury_memory_for_action(user_id, item_id)
