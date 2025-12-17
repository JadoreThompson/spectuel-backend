from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect, WebSocketState

from .connection_manager import ConnectionManager


router = APIRouter(prefix="/ws/orders")
conn_manager = ConnectionManager()


@router.websocket("/")
async def orders_websocket(ws: WebSocket):
    if not conn_manager.is_running:
        conn_manager.launch_listener()

    code = 1000
    reason = None
    user_id = None

    try:
        user_id = await conn_manager.connect(ws)

        while True:
            await ws.receive_text()

    except WebSocketDisconnect as e:
        code = e.code
        reason = e.reason
    finally:
        if user_id is not None:
            conn_manager.disconnect(user_id)
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.close(code, reason)
