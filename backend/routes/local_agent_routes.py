import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# Connected local agents per user
_connected_agents: dict[str, WebSocket] = {}
# Pending requests waiting for responses
_pending_requests: dict[str, asyncio.Future] = {}


@router.websocket("/ws/local-agent")
async def local_agent_websocket(websocket: WebSocket):
    await websocket.accept()
    user_id = websocket.headers.get("X-User-ID", "")

    if not user_id:
        await websocket.close(code=4001, reason="Missing user ID")
        return

    _connected_agents[user_id] = websocket
    print(f"LOCAL_AGENT: Connected for user {user_id}")

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "register":
                print(f"LOCAL_AGENT: Registered {user_id} on {data.get('os')}")

            elif msg_type == "result":
                request_id = data.get("request_id")
                if request_id and request_id in _pending_requests:
                    future = _pending_requests.pop(request_id)
                    if not future.done():
                        future.set_result(data.get("result", {}))

    except WebSocketDisconnect:
        print(f"LOCAL_AGENT: Disconnected for user {user_id}")
    finally:
        _connected_agents.pop(user_id, None)


async def send_local_command(
    user_id: str,
    command: str,
    params: dict = {},
    timeout: float = 15.0,
) -> dict:
    """Send a command to the local agent and wait for the result."""
    ws = _connected_agents.get(user_id)
    if not ws:
        return {
            "success": False,
            "error": "Local agent not connected. Make sure jarvis_local_agent.py is running on your computer.",
        }

    request_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending_requests[request_id] = future

    try:
        await ws.send_text(json.dumps({
            "command": command,
            "params": params,
            "request_id": request_id,
        }))
        result = await asyncio.wait_for(future, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        _pending_requests.pop(request_id, None)
        return {"success": False, "error": "Local agent timed out"}
    except Exception as e:
        _pending_requests.pop(request_id, None)
        return {"success": False, "error": str(e)}
