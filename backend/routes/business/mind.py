"""
The Mind — living memory graph routes (Batch 47).

  GET    /business/mind/graph                — nodes/edges/queue_nodes for the canvas
  GET    /business/mind/gaps                 — dark matter (knowledge gaps)
  GET    /business/mind/activity             — thought-trace activity log (24h replay)
  POST   /business/mind/synapses/generate    — on-demand golden synapse discovery (rate-limited 1/day)
  GET    /business/mind/synapses             — recent golden synapses
  DELETE /business/mind/memories/{memory_id} — "Forget this"
"""
import os

import httpx
from fastapi import APIRouter, HTTPException

from backend.lib.business.mind import gaps as gaps_lib
from backend.lib.business.mind import graph as graph_lib
from backend.lib.business.mind import synapses as synapses_lib

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def _user_id_to_uuid(user_id: str) -> str:
    hex_id = user_id.removeprefix("user_")
    if len(hex_id) == 32 and all(c in "0123456789abcdef" for c in hex_id.lower()):
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    return user_id


@router.get("/business/mind/graph")
async def get_graph(user_id: str = "", limit: int = 300):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await graph_lib.build_graph(user_id, limit=limit)


@router.get("/business/mind/gaps")
async def get_gaps(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"gaps": await gaps_lib.compute_gaps(user_id)}


@router.get("/business/mind/activity")
async def get_activity(user_id: str = "", since: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    if not since:
        raise HTTPException(status_code=400, detail="since required")
    return {"activity": await graph_lib.get_activity(user_id, since)}


@router.post("/business/mind/synapses/generate")
async def generate_synapses_route(user_id: str = "", force: bool = False):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return await synapses_lib.generate_synapses(user_id, force=force)


@router.get("/business/mind/synapses")
async def list_synapses_route(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    return {"synapses": await synapses_lib.list_synapses(user_id)}


@router.delete("/business/mind/memories/{memory_id}")
async def forget_memory(memory_id: str, user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    user_uuid = _user_id_to_uuid(user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{SUPABASE_URL}/rest/v1/business_user_memories",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Prefer": "return=minimal",
            },
            params={"id": f"eq.{memory_id}", "user_id": f"eq.{user_uuid}"},
            timeout=15.0,
        )
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail="delete failed")
    return {"ok": True}
