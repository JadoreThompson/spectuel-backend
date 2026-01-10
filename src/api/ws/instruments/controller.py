import json
import logging
from fastapi import WebSocket

from .connection_manager import ConnectionManager
from .models import RequestType, ResponseType, BarsItem, AckMessage, ErrorMessage
from engine.enums import TimeFrame

logger = logging.getLogger(__name__)


async def handle_subscribe(
    ws: WebSocket,
    conn_manager: ConnectionManager,
    message: dict,
    user_id: str,
    active_subscriptions: dict,
) -> None:
    """Handle subscription requests"""

    # Subscribe to trades
    trades = message.get("trades")
    if trades and isinstance(trades, list):
        trades = [t.upper() for t in trades]
        conn_manager.subscribe_trades(ws, trades)
        active_subscriptions["trades"].update(trades)
        logger.debug(f"User {user_id} subscribed to trades: {trades}")

    # Subscribe to orderbook
    orderbook = message.get("orderbook")
    if orderbook and isinstance(orderbook, list):
        orderbook = [o.upper() for o in orderbook]
        conn_manager.subscribe_orderbook(ws, orderbook)
        active_subscriptions["orderbook"].update(orderbook)
        logger.debug(f"User {user_id} subscribed to orderbook: {orderbook}")

    # Subscribe to bars (OHLC)
    bars = message.get("bars")
    if bars and isinstance(bars, list):
        for bar_item in bars:
            symbol = bar_item.get("symbol", "").upper()
            timeframes_raw = bar_item.get("timeframes", [])

            if not symbol or not timeframes_raw:
                await send_error(
                    ws, "Each bar subscription must have 'symbol' and 'timeframes'"
                )
                continue

            # Convert string timeframes to TimeFrame enum
            timeframes = []
            for tf_str in timeframes_raw:
                try:
                    timeframe = TimeFrame(tf_str.lower())
                    timeframes.append(timeframe)
                except ValueError:
                    await send_error(
                        ws,
                        f"Invalid timeframe: {tf_str}. Valid: {', '.join(TimeFrame._value2member_map_.keys())}",
                    )
                    continue

            if timeframes:
                await conn_manager.subscribe_bars(ws, symbol, timeframes)

                # Track active subscriptions
                if symbol not in active_subscriptions["bars"]:
                    active_subscriptions["bars"][symbol] = set()
                active_subscriptions["bars"][symbol].update(timeframes)

                logger.debug(
                    f"User {user_id} subscribed to bars: {symbol} {[tf.value for tf in timeframes]}"
                )

    await send_ack(ws, RequestType.SUBSCRIBE, active_subscriptions)


async def handle_unsubscribe(
    ws: WebSocket,
    conn_manager: ConnectionManager,
    message: dict,
    user_id: str,
    active_subscriptions: dict,
) -> None:
    """Handle unsubscription requests"""

    # Unsubscribe from trades
    trades = message.get("trades")
    if trades and isinstance(trades, list):
        trades = [t.upper() for t in trades]
        conn_manager.unsubscribe_trades(ws, trades)
        active_subscriptions["trades"].difference_update(trades)
        logger.debug(f"User {user_id} unsubscribed from trades: {trades}")

    # Unsubscribe from orderbook
    orderbook = message.get("orderbook")
    if orderbook and isinstance(orderbook, list):
        orderbook = [o.upper() for o in orderbook]
        conn_manager.unsubscribe_orderbook(ws, orderbook)
        active_subscriptions["orderbook"].difference_update(orderbook)
        logger.debug(f"User {user_id} unsubscribed from orderbook: {orderbook}")

    # Unsubscribe from bars (OHLC)
    bars = message.get("bars")
    if bars and isinstance(bars, list):
        for bar_item in bars:
            symbol = bar_item.get("symbol", "").upper()
            timeframes_raw = bar_item.get("timeframes", [])

            if not symbol:
                await send_error(ws, "Bar unsubscription requires 'symbol'")
                continue

            # Convert string timeframes to TimeFrame enum
            timeframes = []
            for tf_str in timeframes_raw:
                try:
                    timeframe = TimeFrame(tf_str.lower())
                    timeframes.append(timeframe)
                except ValueError:
                    await send_error(ws, f"Invalid timeframe: {tf_str}")
                    continue

            if timeframes:
                conn_manager.unsubscribe_bars(ws, symbol, timeframes)

                # Update active subscriptions
                if symbol in active_subscriptions["bars"]:
                    active_subscriptions["bars"][symbol].difference_update(timeframes)
                    if not active_subscriptions["bars"][symbol]:
                        del active_subscriptions["bars"][symbol]

                logger.debug(
                    f"User {user_id} unsubscribed from bars: {symbol} {[tf.value for tf in timeframes]}"
                )

    await send_ack(ws, RequestType.UNSUBSCRIBE, active_subscriptions)


async def cleanup_subscriptions(
    ws: WebSocket, conn_manager: ConnectionManager, active_subscriptions: dict
) -> None:
    """Clean up all subscriptions when client disconnects"""

    # Unsubscribe from all active subscriptions
    if active_subscriptions["trades"]:
        conn_manager.unsubscribe_trades(ws, list(active_subscriptions["trades"]))

    if active_subscriptions["orderbook"]:
        conn_manager.unsubscribe_orderbook(ws, list(active_subscriptions["orderbook"]))

    for symbol, timeframes in active_subscriptions["bars"].items():
        if timeframes:
            conn_manager.unsubscribe_bars(ws, symbol, list(timeframes))


async def send_ack(
    ws: WebSocket, request_type: RequestType, active_subscriptions: dict
) -> None:
    """Send acknowledgment with current subscriptions"""
    try:
        bars_data = [
            {
                "symbol": symbol,
                "timeframes": [tf.value for tf in timeframes],
            }
            for symbol, timeframes in active_subscriptions["bars"].items()
        ]

        ack_msg = AckMessage(
            type=ResponseType.ACK,
            request_type=request_type,
            subscriptions={
                "trades": list(active_subscriptions["trades"]),
                "orderbook": list(active_subscriptions["orderbook"]),
                "bars": bars_data,
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