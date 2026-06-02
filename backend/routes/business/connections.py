"""
API for connector management.

  GET    /business/connections/manifests  → list of available connector types + their required fields
  GET    /business/connections            → list of user's connections (with status)
  POST   /business/connections            → upsert credentials + run test immediately
  POST   /business/connections/test       → test an existing connection
  DELETE /business/connections            → remove a connection
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.lib.business.connectors.registry import (
    list_available_connectors,
    list_user_connections,
    upsert_user_connection,
    get_connector_for_user,
    delete_user_connection,
    update_test_result,
    connector_class,
)

router = APIRouter()


@router.get("/business/connections/manifests")
async def get_manifests():
    return {"connectors": list_available_connectors()}


@router.get("/business/connections")
async def get_user_connections(user_id: str = ""):
    if not user_id:
        return {"connections": []}
    rows = await list_user_connections(user_id)
    return {"connections": rows}


class UpsertConnectionRequest(BaseModel):
    user_id: str
    connector_type: str
    credentials: dict
    display_name: str = ""


@router.post("/business/connections")
async def upsert_connection(request: UpsertConnectionRequest):
    if not request.user_id or not request.connector_type:
        raise HTTPException(status_code=400, detail="user_id and connector_type required")
    cls = connector_class(request.connector_type)
    if not cls:
        raise HTTPException(status_code=400, detail=f"Unknown connector_type: {request.connector_type}")

    # Save first (so even if test fails, credentials are stored — user can retry)
    row = await upsert_user_connection(
        user_id=request.user_id,
        connector_type=request.connector_type,
        credentials=request.credentials,
        display_name=request.display_name or cls.DISPLAY_NAME,
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to save connection")

    # Now test
    instance = cls(credentials=request.credentials)
    result = await instance.test()
    await update_test_result(request.user_id, request.connector_type, result)

    return {
        "ok": result.ok,
        "error": result.error,
        "data": result.data,
        "connection_id": row.get("id"),
    }


class TestConnectionRequest(BaseModel):
    user_id: str
    connector_type: str


@router.post("/business/connections/test")
async def test_connection(request: TestConnectionRequest):
    if not request.user_id or not request.connector_type:
        raise HTTPException(status_code=400, detail="user_id and connector_type required")
    instance = await get_connector_for_user(request.user_id, request.connector_type)
    if not instance:
        raise HTTPException(status_code=404, detail="Connection not found or inactive")
    result = await instance.test()
    await update_test_result(request.user_id, request.connector_type, result)
    return {"ok": result.ok, "error": result.error, "data": result.data}


class DeleteConnectionRequest(BaseModel):
    user_id: str
    connector_type: str


@router.delete("/business/connections")
async def delete_connection(request: DeleteConnectionRequest):
    ok = await delete_user_connection(request.user_id, request.connector_type)
    return {"ok": ok}
