import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from .connection_manager import ConnectionManager
from .controller import (
    cleanup_subscriptions,
    handle_subscribe,
    handle_unsubscribe,
    send_error,
)
from .models import RequestType, ResponseType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/instruments")
conn_manager = ConnectionManager()


@router.websocket("/")
async def instruments_websocket(ws: WebSocket):
    """
    WebSocket endpoint for real-time instrument data.

    Client can send:
    {
        "type": "subscribe" | "unsubscribe",
        "trades": ["AAPL", "MSFT"],
        "orderbook": ["AAPL"],
        "bars": [
            {"symbol": "AAPL", "timeframes": ["5m", "15m"]},
            {"symbol": "MSFT", "timeframes": ["1h"]}
        ]
    }

    Server sends:
    - ack: Confirms subscription/unsubscription
    - error: Validation or processing errors
    - trade: New trade event
    - ohlc_snapshot: Historical OHLC data on subscription
    - ohlc_update: Real-time OHLC update
    - orderbook_snapshot: Orderbook snapshot
    """

    code = 1000
    reason = None
    user_id = None
    active_subscriptions = {
        "trades": set(),
        "orderbook": set(),
        "bars": {},
    }

    try:
        await conn_manager.connect(ws)
        logger.info(f"User {user_id} connected")

        while True:
            # Receive message from client
            data = await ws.receive_text()

            try:
                msg: dict = json.loads(data)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from {user_id}: {e}")
                await send_error(ws, "Invalid JSON format")
                continue

            request_type_raw = msg.get("type")

            # Validate request type
            try:
                request_type = RequestType(request_type_raw)
            except ValueError:
                logger.warning(
                    f"Unknown request type from {user_id}: {request_type_raw}"
                )
                await send_error(
                    ws,
                    f"Invalid request type. Must be: {', '.join([t.value for t in RequestType])}",
                )
                continue

            if request_type == RequestType.SUBSCRIBE:
                await handle_subscribe(
                    ws, conn_manager, msg, user_id, active_subscriptions
                )
            elif request_type == RequestType.UNSUBSCRIBE:
                await handle_unsubscribe(
                    ws, conn_manager, msg, user_id, active_subscriptions
                )

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
            await cleanup_subscriptions(ws, conn_manager, active_subscriptions)
            conn_manager.disconnect(ws)
            logger.info(f"Cleaned up subscriptions for {user_id}")

        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close(code, reason)
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
