from fastapi import APIRouter
from backend.user_model import get_user_model

router = APIRouter()


@router.get("/user/onboarding-status/{user_id}")
async def onboarding_status(user_id: str):
    model, _ = await get_user_model(user_id)
    return {
        "user_id": user_id,
        "onboarding_complete": model.get("onboarding_complete", False),
        "interaction_count": model["jarvis_relationship"]["interaction_count"],
        "trust_level": model["jarvis_relationship"]["trust_level"],
    }


@router.get("/user/model/{user_id}")
async def get_full_model(user_id: str):
    model, _ = await get_user_model(user_id)
    return model
