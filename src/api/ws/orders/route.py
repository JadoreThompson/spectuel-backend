import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from api.ws.exc import AuthenticationError
from .connection_manager import ConnectionManager
from .controller import (
    cleanup_subscriptions,
    handle_subscribe,
    handle_unsubscribe,
    send_error,
)
from .models import RequestType, ResponseType, AckMessage


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/orders")
conn_manager = ConnectionManager()


@router.websocket("/")
async def orders_websocket(ws: WebSocket):
    code = 1000
    reason = None
    user_id: str | None = None
    active_subscriptions = {
        "order_events": set(),
        "balance_events": set(),
    }

    try:
        # Authenticate user
        user_id = await conn_manager.connect(ws)
        logger.info(f"User {user_id} connected")

        await ws.send_text(
            AckMessage(
                type=ResponseType.ACK,
                request_type=RequestType.AUTHENTICATE,
                message="Successfully authenticated",
            ).model_dump_json()
        )

        while True:
            # Receive message from client
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
                continue

            try:
                msg: dict = json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from {user_id}: {e}")
                await send_error(ws, "Invalid JSON format")
                continue

            request_type = msg.get("type")

            if request_type == RequestType.SUBSCRIBE:
                await handle_subscribe(
                    ws, conn_manager, msg, user_id, active_subscriptions
                )
            elif request_type == RequestType.UNSUBSCRIBE:
                await handle_unsubscribe(
                    ws, conn_manager, msg, user_id, active_subscriptions
                )
            elif request_type == RequestType.AUTHENTICATE:
                await send_error(ws, "Already authenticated")

    except AuthenticationError as e:
        code = 1008
        reason = str(e)
        logger.warning(f"Authentication error: {e}")
        await send_error(ws, str(e))
    except WebSocketDisconnect as e:
        code = e.code
        reason = e.reason
        logger.info(f"User {user_id} disconnected: code={code}, reason={reason}")
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        code = 1011
        reason = "Server error"
    finally:
        if user_id is not None:
            await cleanup_subscriptions(user_id, conn_manager, active_subscriptions)
            conn_manager.disconnect(user_id)
            logger.info(f"Cleaned up connection for {user_id}")

        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close(code, reason)
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
