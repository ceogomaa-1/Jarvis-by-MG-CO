import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

router = APIRouter()

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def user_id_to_uuid(user_id: str) -> str:
    """Convert 'user_abc123...' to UUID format 'abc123de-f456-...'"""
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


class CreateConversationRequest(BaseModel):
    user_id: str


class UpdateConversationRequest(BaseModel):
    user_id: str
    title: str | None = None
    is_archived: bool | None = None


class SaveMessageRequest(BaseModel):
    user_id: str
    role: str
    content: str


@router.get("/business/conversations")
def list_conversations(user_id: str):
    sb = _get_supabase()
    if not sb or not user_id:
        return {"conversations": []}
    uuid = user_id_to_uuid(user_id)
    try:
        res = (
            sb.table("business_conversations")
            .select("id, title, updated_at, created_at")
            .eq("user_id", uuid)
            .eq("is_archived", False)
            .order("updated_at", desc=True)
            .limit(50)
            .execute()
        )
        return {"conversations": res.data or []}
    except Exception as e:
        print(f"list_conversations error: {e}")
        return {"conversations": []}


@router.post("/business/conversations")
def create_conversation(req: CreateConversationRequest):
    sb = _get_supabase()
    if not sb:
        raise HTTPException(status_code=500, detail="DB unavailable")
    uuid = user_id_to_uuid(req.user_id)
    try:
        res = (
            sb.table("business_conversations")
            .insert({"user_id": uuid, "title": "New conversation"})
            .execute()
        )
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create conversation")
        return {"conversation": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/business/conversations/{conv_id}")
def get_conversation(conv_id: str, user_id: str):
    sb = _get_supabase()
    if not sb:
        return {"conversation": None, "messages": []}
    uuid = user_id_to_uuid(user_id)
    try:
        conv = (
            sb.table("business_conversations")
            .select("*")
            .eq("id", conv_id)
            .eq("user_id", uuid)
            .maybe_single()
            .execute()
        )
        msgs = (
            sb.table("business_messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conv_id)
            .order("created_at", desc=False)
            .execute()
        )
        return {"conversation": conv.data, "messages": msgs.data or []}
    except Exception as e:
        print(f"get_conversation error: {e}")
        return {"conversation": None, "messages": []}


@router.patch("/business/conversations/{conv_id}")
def update_conversation(conv_id: str, req: UpdateConversationRequest):
    sb = _get_supabase()
    if not sb:
        return {"ok": True}
    update: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if req.title is not None:
        update["title"] = req.title
    if req.is_archived is not None:
        update["is_archived"] = req.is_archived
    try:
        res = sb.table("business_conversations").update(update).eq("id", conv_id).execute()
        return {"conversation": res.data[0] if res.data else None}
    except Exception as e:
        print(f"update_conversation error: {e}")
        return {"ok": False}


@router.delete("/business/conversations/{conv_id}")
def delete_conversation(conv_id: str, user_id: str):
    sb = _get_supabase()
    if not sb:
        return {"ok": True}
    try:
        sb.table("business_conversations").update({"is_archived": True}).eq("id", conv_id).execute()
    except Exception as e:
        print(f"delete_conversation error: {e}")
    return {"ok": True}


@router.post("/business/conversations/{conv_id}/messages")
def save_message_to_conversation(conv_id: str, req: SaveMessageRequest):
    sb = _get_supabase()
    if not sb:
        return {"ok": True}
    try:
        res = (
            sb.table("business_messages")
            .insert({"conversation_id": conv_id, "role": req.role, "content": req.content})
            .execute()
        )
        return {"message": res.data[0] if res.data else None}
    except Exception as e:
        print(f"save_message error: {e}")
        return {"ok": False}


@router.get("/business/agents/activity")
def get_agents_activity(user_id: str = ""):
    """Return recent activity for all 10 workflow agents."""
    sb = _get_supabase()

    AGENT_IDS = [
        "operator-strategist", "operator-researcher",
        "operator-creator", "operator-packager",
        "creation-strategist", "creation-copywriter",
        "creation-designer", "creation-researcher",
        "creation-analyst", "creation-reporter",
    ]
    agents: dict = {aid: {"status": "idle", "last_run": None, "recent_activity": [], "last_output": None} for aid in AGENT_IDS}

    if not sb or not user_id:
        return {"agents": agents}

    uuid = user_id_to_uuid(user_id)

    # Query operator runs
    try:
        res = (
            sb.table("business_operator_runs")
            .select("agent_id, status, created_at, summary, output")
            .eq("user_id", uuid)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        runs = res.data or []
        seen: dict[str, list] = {}
        for run in runs:
            aid = run.get("agent_id", "")
            if aid not in agents:
                continue
            if aid not in seen:
                seen[aid] = []
                agents[aid]["last_run"] = run.get("created_at")
                agents[aid]["status"] = run.get("status", "idle")
                agents[aid]["last_output"] = run.get("output")
            if len(seen[aid]) < 3:
                seen[aid].append({
                    "time": run.get("created_at", ""),
                    "summary": run.get("summary", ""),
                })
                agents[aid]["recent_activity"] = seen[aid]
    except Exception:
        pass

    return {"agents": agents}


@router.get("/business/memories/count")
def get_memory_count(user_id: str):
    sb = _get_supabase()
    if not sb or not user_id:
        return {"count": 0}
    uuid = user_id_to_uuid(user_id)
    try:
        res = (
            sb.table("business_user_memories")
            .select("id")
            .eq("user_id", uuid)
            .limit(500)
            .execute()
        )
        return {"count": len(res.data or [])}
    except Exception as e:
        print(f"get_memory_count error: {e}")
        return {"count": 0}
