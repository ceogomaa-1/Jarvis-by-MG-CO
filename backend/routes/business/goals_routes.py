"""HTTP surface for the Rue OS1 Goal Engine control plane."""
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.lib.business import goal_engine

router = APIRouter()


def _trusted_user_id(request: Request, claimed: str) -> str:
    if not claimed:
        raise HTTPException(status_code=400, detail="user_id required")
    authenticated = getattr(request.state, "auth_user_id", None)
    if authenticated and authenticated != claimed:
        raise HTTPException(status_code=403, detail="Identity does not match access token")
    return authenticated or claimed


def _engine_error(exc: Exception) -> HTTPException:
    if isinstance(exc, goal_engine.GoalConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=503, detail=str(exc))


class CreateGoalRequest(BaseModel):
    user_id: str
    objective: str = Field(min_length=5, max_length=500)
    metric_key: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_]+$")
    unit: str = Field(default="count", max_length=30)
    direction: Literal["increase", "decrease"] = "increase"
    baseline_value: float = 0
    current_value: float | None = None
    target_value: float
    deadline: datetime
    confidence: float = Field(default=0.5, ge=0, le=1)
    constraints: list[Any] = Field(default_factory=list, max_length=20)
    leading_indicators: list[Any] = Field(default_factory=list, max_length=20)

    @field_validator("deadline")
    @classmethod
    def deadline_must_be_future(cls, value: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        comparable = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if comparable <= now:
            raise ValueError("deadline must be in the future")
        return comparable

    @field_validator("objective")
    @classmethod
    def objective_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("objective cannot be blank")
        return value.strip()


class UpdateGoalRequest(BaseModel):
    user_id: str
    objective: str | None = Field(default=None, min_length=5, max_length=500)
    target_value: float | None = None
    current_value: float | None = None
    deadline: datetime | None = None
    status: Literal["draft", "active", "paused", "achieved", "missed", "cancelled"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    constraints: list[Any] | None = Field(default=None, max_length=20)
    leading_indicators: list[Any] | None = Field(default=None, max_length=20)


class MetricObservationRequest(BaseModel):
    user_id: str
    value: float
    observed_at: datetime | None = None
    source_type: str = Field(default="manual", max_length=50)
    source_ref: str | None = Field(default=None, max_length=300)
    idempotency_key: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    metric_key: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9_]+$")


@router.get("/business/goals")
async def goals_index(request: Request, user_id: str, status: str | None = None):
    user_id = _trusted_user_id(request, user_id)
    if status and status not in {"draft", "active", "paused", "achieved", "missed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Invalid goal status")
    try:
        return {"goals": await goal_engine.list_goals(user_id, status=status)}
    except Exception as exc:
        raise _engine_error(exc) from exc


@router.post("/business/goals", status_code=201)
async def goals_create(request: Request, body: CreateGoalRequest):
    user_id = _trusted_user_id(request, body.user_id)
    if body.target_value == body.baseline_value:
        raise HTTPException(status_code=400, detail="target_value must differ from baseline_value")
    payload = body.model_dump(exclude={"user_id"})
    payload["deadline"] = body.deadline.isoformat()
    if body.current_value is None:
        payload["current_value"] = body.baseline_value
    try:
        return {"goal": await goal_engine.create_goal(user_id, payload)}
    except Exception as exc:
        raise _engine_error(exc) from exc


@router.get("/business/goals/command-center")
async def goals_command_center(request: Request, user_id: str):
    user_id = _trusted_user_id(request, user_id)
    try:
        snapshot = await goal_engine.get_active_goal_snapshot(user_id)
        return {"snapshot": snapshot, "configured": snapshot is not None}
    except Exception as exc:
        raise _engine_error(exc) from exc


@router.get("/business/goals/{goal_id}")
async def goals_get(goal_id: str, request: Request, user_id: str):
    user_id = _trusted_user_id(request, user_id)
    try:
        goal = await goal_engine.get_goal(user_id, goal_id)
    except Exception as exc:
        raise _engine_error(exc) from exc
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"goal": goal}


@router.patch("/business/goals/{goal_id}")
async def goals_update(goal_id: str, request: Request, body: UpdateGoalRequest):
    user_id = _trusted_user_id(request, body.user_id)
    payload = body.model_dump(exclude={"user_id"}, exclude_none=True)
    if body.deadline:
        payload["deadline"] = body.deadline.isoformat()
    try:
        goal = await goal_engine.update_goal(user_id, goal_id, payload)
    except Exception as exc:
        raise _engine_error(exc) from exc
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"goal": goal}


@router.post("/business/goals/{goal_id}/observations", status_code=201)
async def goals_observe(goal_id: str, request: Request, body: MetricObservationRequest):
    user_id = _trusted_user_id(request, body.user_id)
    try:
        result = await goal_engine.record_metric_observation(
            user_id,
            goal_id,
            body.value,
            observed_at=body.observed_at.isoformat() if body.observed_at else None,
            source_type=body.source_type,
            source_ref=body.source_ref,
            idempotency_key=body.idempotency_key,
            metadata=body.metadata,
            metric_key=body.metric_key,
        )
        return result
    except Exception as exc:
        raise _engine_error(exc) from exc


@router.get("/business/initiatives")
async def initiatives_index(
    request: Request,
    user_id: str,
    goal_id: str | None = None,
    limit: int = 30,
):
    user_id = _trusted_user_id(request, user_id)
    try:
        initiatives = await goal_engine.list_initiatives(user_id, goal_id=goal_id, limit=limit)
        return {"initiatives": initiatives}
    except Exception as exc:
        raise _engine_error(exc) from exc


@router.get("/business/experiments")
async def experiments_index(
    request: Request,
    user_id: str,
    goal_id: str | None = None,
    limit: int = 30,
):
    user_id = _trusted_user_id(request, user_id)
    try:
        experiments = await goal_engine.list_experiments(user_id, goal_id=goal_id, limit=limit)
        return {"experiments": experiments}
    except Exception as exc:
        raise _engine_error(exc) from exc
