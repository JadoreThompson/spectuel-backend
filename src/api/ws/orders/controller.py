import logging

from fastapi import WebSocket

from .connection_manager import ConnectionManager
from .models import (
    RequestType,
    ResponseType,
    AckMessage,
    ErrorMessage,
)

logger = logging.getLogger(__name__)


async def handle_subscribe(
    ws: WebSocket,
    conn_manager: ConnectionManager,
    message: dict,
    user_id: str,
    active_subscriptions: dict,
) -> None:
    """Handle subscription requests"""

    # Subscribe to order events
    order_events = message.get("order_events")
    if order_events and isinstance(order_events, list):
        try:
            conn_manager.subscribe_order_events(user_id, order_events)
            active_subscriptions["order_events"].update(order_events)
            logger.debug(f"User {user_id} subscribed to order events: {order_events}")
        except ValueError as e:
            await send_error(ws, str(e))

    # Subscribe to balance events
    balance_events = message.get("balance_events")
    if balance_events and isinstance(balance_events, list):
        try:
            conn_manager.subscribe_balance_events(user_id, balance_events)
            active_subscriptions["balance_events"].update(balance_events)
            logger.debug(
                f"User {user_id} subscribed to balance events: {balance_events}"
            )
        except ValueError as e:
            await send_error(ws, str(e))

    await send_ack(ws, RequestType.SUBSCRIBE, active_subscriptions)


async def handle_unsubscribe(
    ws: WebSocket,
    conn_manager: ConnectionManager,
    message: dict,
    user_id: str,
    active_subscriptions: dict,
) -> None:
    """Handle unsubscription requests"""

    # Unsubscribe from order events
    order_events = message.get("order_events")
    if order_events and isinstance(order_events, list):
        try:
            conn_manager.unsubscribe_order_events(user_id, order_events)
            active_subscriptions["order_events"].difference_update(order_events)
            logger.debug(
                f"User {user_id} unsubscribed from order events: {order_events}"
            )
        except ValueError as e:
            await send_error(ws, str(e))

    # Unsubscribe from balance events
    balance_events = message.get("balance_events")
    if balance_events and isinstance(balance_events, list):
        try:
            conn_manager.unsubscribe_balance_events(user_id, balance_events)
            active_subscriptions["balance_events"].difference_update(balance_events)
            logger.debug(
                f"User {user_id} unsubscribed from balance events: {balance_events}"
            )
        except ValueError as e:
            await send_error(ws, str(e))

    await send_ack(ws, RequestType.UNSUBSCRIBE, active_subscriptions)


async def cleanup_subscriptions(
    user_id: str, conn_manager: ConnectionManager, active_subscriptions: dict
) -> None:
    """Clean up all subscriptions when client disconnects"""

    if active_subscriptions["order_events"]:
        conn_manager.unsubscribe_order_events(
            user_id, list(active_subscriptions["order_events"])
        )

    if active_subscriptions["balance_events"]:
        conn_manager.unsubscribe_balance_events(
            user_id, list(active_subscriptions["balance_events"])
        )

    logger.debug(f"Cleaned up subscriptions for user {user_id}")


async def send_ack(
    ws: WebSocket, request_type: RequestType, active_subscriptions: dict
) -> None:
    """Send acknowledgment with current subscriptions"""
    try:
        ack_msg = AckMessage(
            type=ResponseType.ACK,
            request_type=request_type,
            subscriptions={
                "order_events": list(active_subscriptions["order_events"]),
                "balance_events": list(active_subscriptions["balance_events"]),
            },
        )

        await ws.send_text(ack_msg.model_dump_json())
    except Exception as e:
        logger.error(f"Error sending ack: {e}")


async def send_error(ws: WebSocket, message: str) -> None:
    """Send error message to client"""
    try:
        error_msg = ErrorMessage(
            type=ResponseType.ERROR,
            message=message,
        )
        await ws.send_text(error_msg.model_dump_json())
    except Exception as e:
        logger.error(f"Error sending error message: {e}")
