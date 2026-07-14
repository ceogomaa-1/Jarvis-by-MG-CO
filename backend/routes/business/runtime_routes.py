"""Operational API for the durable Rue OS1 runtime."""
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.lib.business.runtime import store
from backend.lib.business.runtime.worker import dispatch_runtime_tick

router = APIRouter()


def _trusted_user_id(request: Request, claimed: str) -> str:
    if not claimed:
        raise HTTPException(status_code=400, detail="user_id required")
    authenticated = getattr(request.state, "auth_user_id", None)
    if authenticated and authenticated != claimed:
        raise HTTPException(status_code=403, detail="Identity does not match access token")
    return authenticated or claimed


class EmitEventRequest(BaseModel):
    user_id: str
    event_type: str = Field(min_length=3, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=3, max_length=240)
    source: str = Field(default="api", max_length=80)
    subject_type: str | None = Field(default=None, max_length=80)
    subject_id: str | None = Field(default=None, max_length=200)


@router.get("/business/runtime/workflows")
async def workflows_index(request: Request, user_id: str, limit: int = 30):
    user_id = _trusted_user_id(request, user_id)
    try:
        return {"workflows": await store.list_workflows(user_id, limit=limit)}
    except store.RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/business/runtime/workflows/{workflow_id}")
async def workflows_get(workflow_id: str, request: Request, user_id: str):
    user_id = _trusted_user_id(request, user_id)
    try:
        workflow = await store.get_workflow(user_id, workflow_id)
    except store.RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"workflow": workflow}


@router.post("/business/runtime/events", status_code=202)
async def events_create(request: Request, body: EmitEventRequest):
    user_id = _trusted_user_id(request, body.user_id)
    payload = {**body.payload, "user_id": user_id}
    try:
        event = await store.emit_event(
            user_id,
            body.event_type,
            payload,
            idempotency_key=body.idempotency_key,
            source=body.source,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
        )
        return {"event": event}
    except store.RuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/business/runtime/_dispatch")
async def runtime_dispatch(x_cron_secret: str | None = Header(default=None)):
    """External-pinger recovery hook. The in-process scheduler calls the same
    dispatcher; this endpoint is useful when the web service has been sleeping."""
    expected = os.getenv("OS1_RUNTIME_CRON_SECRET") or os.getenv("CRON_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="External runtime dispatch is disabled")
    if x_cron_secret != expected:
        raise HTTPException(status_code=403, detail="Invalid cron secret")
    return await dispatch_runtime_tick()
