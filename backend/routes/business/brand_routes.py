"""
Brand config API.

  GET  /business/brand?user_id=...  → get brand config
  POST /business/brand              → upsert brand config
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib.business.brand_config import get_brand_config, upsert_brand_config

router = APIRouter()


@router.get("/business/brand")
async def get_brand(user_id: str = ""):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    config = await get_brand_config(user_id)
    return {"brand": config}


class BrandUpsertRequest(BaseModel):
    user_id: str
    logo_url: str | None = None
    banner_url: str | None = None
    accent_color: str | None = None
    display_name: str | None = None
    north_star_target_usd: float | None = None
    north_star_target_label: str | None = None
    operator_enabled: bool | None = None
    operator_daily_budget_usd: float | None = None


@router.post("/business/brand")
async def upsert_brand(request: BrandUpsertRequest):
    if not request.user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    fields = {k: v for k, v in request.model_dump().items() if k != "user_id" and v is not None}
    result = await upsert_brand_config(request.user_id, fields)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to save brand config")
    return {"brand": result}
