from fastapi import APIRouter
from backend.agent import get_notes, mark_note_done, _load_notes

router = APIRouter()


@router.get("/notes/{user_id}")
async def list_notes(user_id: str):
    notes = _load_notes(user_id)
    active = [n for n in notes if not n.get("done")]
    return {"user_id": user_id, "count": len(active), "notes": active}


@router.post("/notes/{user_id}/done/{note_id}")
async def complete_note(user_id: str, note_id: str):
    result = await mark_note_done(user_id, note_id)
    return {"result": result}
