import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from config import KAFKA_INSTRUMENT_EVENTS_TOPIC, REDIS_CANDLE_CACHE_PREFIX
from engine.enums import InstrumentEventType, TimeFrame
from infra.kafka import AsyncKafkaConsumer, AsyncKafkaProducer
from infra.redis import REDIS_CLIENT
from .models import ResponseType, OHLCMessage, OHLCData, TradeMessage

logger = logging.getLogger(__name__)

# Timeframe to seconds mapping
TIMEFRAME_SECONDS = {
    TimeFrame.M5: 300,
    TimeFrame.M15: 900,
    TimeFrame.H1: 3600,
    TimeFrame.H4: 14400,
    TimeFrame.D1: 86400,
}


class OHLC:
    """Represents an OHLC candle"""

    def __init__(self, open_price: float, timestamp: int):
        self.open = open_price
        self.high = open_price
        self.low = open_price
        self.close = open_price
        self.volume = 0.0
        self.timestamp = timestamp

    def update(self, price: float, quantity: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += quantity

    def to_dict(self) -> dict:
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "timestamp": self.timestamp,
        }


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts trade/OHLC events.
    Uses weak references and event-driven cleanup to avoid O(n) operations.
    """

    def __init__(self) -> None:
        # {symbol: {timeframe: {ws1, ws2, ...}}}
        self._bar_conns: dict[str, dict[TimeFrame, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        # {symbol: {ws1, ws2, ...}}
        self._trade_conns: dict[str, set[WebSocket]] = defaultdict(set)
        # {symbol: {ws1, ws2, ...}}
        self._ob_conns: dict[str, set[WebSocket]] = defaultdict(set)

        # OHLC state: {symbol: {timeframe: OHLC}}
        self._ohlc_state: dict[str, dict[TimeFrame, OHLC]] = defaultdict(dict)

        # Track closed connections for cleanup
        self._closed_connections: asyncio.Queue[WebSocket] = asyncio.Queue()

        self._producer = AsyncKafkaProducer()
        self._is_running = False
        self._launch_listener()
        self._launch_cleanup_worker()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        self._is_running = True

    def _launch_listener(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._listen_to_kafka())
        except RuntimeError:
            logger.warning("No running event loop to launch listener")

    def _launch_cleanup_worker(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._cleanup_closed_connections())
        except RuntimeError:
            logger.warning("No running event loop to launch cleanup worker")

    async def connect(self, ws: WebSocket) -> str:
        """Accept and register a new WebSocket connection"""
        await ws.accept()
        return str(id(ws))

    def disconnect(self, ws: WebSocket) -> None:
        """Mark connection for cleanup"""
        self._closed_connections.put_nowait(ws)

    def subscribe_trades(self, ws: WebSocket, symbols: list[str]) -> None:
        """Subscribe a connection to trade events for symbols"""
        for symbol in symbols:
            self._trade_conns[symbol].add(ws)

    def subscribe_orderbook(self, ws: WebSocket, symbols: list[str]) -> None:
        """Subscribe a connection to orderbook events for symbols"""
        for symbol in symbols:
            self._ob_conns[symbol].add(ws)

    async def subscribe_bars(
        self, ws: WebSocket, symbol: str, timeframes: list[TimeFrame]
    ) -> None:
        """Subscribe a connection to OHLC events for symbol+timeframes"""
        for timeframe in timeframes:
            self._bar_conns[symbol][timeframe].add(ws)

            # Send latest cached OHLC if available
            redis_key = f"{REDIS_CANDLE_CACHE_PREFIX}:{symbol}:{timeframe.value}"
            cached = await REDIS_CLIENT.get(redis_key)

            if cached:
                ohlc_dict = json.loads(cached)
                ohlc_data = OHLCData(**ohlc_dict)
                msg = OHLCMessage(
                    type=ResponseType.OHLC_SNAPSHOT,
                    symbol=symbol,
                    timeframe=timeframe.value,
                    ohlc=ohlc_data,
                )
                await self._send_to_client(ws, msg.model_dump_json())

    def unsubscribe_trades(self, ws: WebSocket, symbols: list[str]) -> None:
        """Unsubscribe from trade events"""
        for symbol in symbols:
            self._trade_conns[symbol].discard(ws)

    def unsubscribe_orderbook(self, ws: WebSocket, symbols: list[str]) -> None:
        """Unsubscribe from orderbook events"""
        for symbol in symbols:
            self._ob_conns[symbol].discard(ws)

    def unsubscribe_bars(
        self, ws: WebSocket, symbol: str, timeframes: list[TimeFrame]
    ) -> None:
        """Unsubscribe from OHLC events"""
        for timeframe in timeframes:
            self._bar_conns[symbol][timeframe].discard(ws)

    async def _send_to_client(self, ws: WebSocket, message: str) -> None:
        """
        Send message to a client with connection check.
        If send fails, mark for cleanup.
        """
        try:
            if ws.client_state != WebSocketState.CONNECTED:
                await self._closed_connections.put(ws)
                return

            await asyncio.wait_for(ws.send_text(message), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Send timeout - client too slow")
            await self._closed_connections.put(ws)
        except Exception as e:
            logger.error(f"Send error: {e}")
            await self._closed_connections.put(ws)

    async def _broadcast_to_set(self, clients: set[WebSocket], message: str) -> None:
        """Broadcast to a set of clients without blocking"""
        # Create snapshot to avoid modification during iteration
        clients_snapshot = list(clients)

        tasks = [self._send_to_client(client, message) for client in clients_snapshot]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _cleanup_closed_connections(self) -> None:
        """
        Background worker that removes closed connections from all subscription lists.
        This is O(1) per closed connection, not O(n).
        """
        while True:
            try:
                # Wait for a closed connection with timeout
                ws = await self._closed_connections.get()

                # Remove from all subscription lists
                for symbols_dict in self._bar_conns.values():
                    for timeframe_set in symbols_dict.values():
                        timeframe_set.discard(ws)

                for symbol_set in self._trade_conns.values():
                    symbol_set.discard(ws)

                for symbol_set in self._ob_conns.values():
                    symbol_set.discard(ws)

            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    def _get_candle_timestamp(self, current_ts: int, timeframe: TimeFrame) -> int:
        """
        Get the start timestamp of the current candle.
        For example, with 5-minute candles, 09:37 belongs to 09:35-09:40.
        """
        timeframe_seconds = TIMEFRAME_SECONDS[timeframe]
        return (current_ts // timeframe_seconds) * timeframe_seconds

    async def _process_trade_event(self, event: dict) -> None:
        """Process a new trade event and update OHLC/broadcast"""
        symbol = event["symbol"]
        price = event["price"]
        quantity = event["quantity"]
        trade_timestamp = event.get("timestamp", int(datetime.now().timestamp()))

        # Broadcast to trade subscribers (no filtering by timestamp)
        trade_msg = TradeMessage(
            type=ResponseType.TRADE,
            symbol=symbol,
            price=price,
            quantity=quantity,
            timestamp=trade_timestamp,
            command_id=event.get("command_id"),
            order_id=event.get("order_id"),
            role=event.get("role"),
        )

        if symbol in self._trade_conns and self._trade_conns[symbol]:
            await self._broadcast_to_set(
                self._trade_conns[symbol], trade_msg.model_dump_json()
            )

        # Update OHLC for all subscribed timeframes for this symbol
        if symbol in self._bar_conns:
            for timeframe in self._bar_conns[symbol].keys():
                if not self._bar_conns[symbol][timeframe]:
                    # No subscribers for this timeframe, skip
                    continue

                timeframe_seconds = TIMEFRAME_SECONDS[timeframe]
                candle_ts = self._get_candle_timestamp(trade_timestamp, timeframe)

                # Get or create current OHLC
                if timeframe not in self._ohlc_state[symbol]:
                    self._ohlc_state[symbol][timeframe] = OHLC(price, candle_ts)
                else:
                    ohlc = self._ohlc_state[symbol][timeframe]
                    # Check if we need a new candle
                    if ohlc.timestamp + timeframe_seconds <= trade_timestamp:
                        # New candle - cache the old one
                        redis_key = (
                            f"{REDIS_CANDLE_CACHE_PREFIX}:{symbol}:{timeframe.value}"
                        )
                        await REDIS_CLIENT.set(
                            redis_key, json.dumps(ohlc.to_dict()), ex=86400
                        )

                        # Create new candle
                        self._ohlc_state[symbol][timeframe] = OHLC(price, candle_ts)
                        ohlc = self._ohlc_state[symbol][timeframe]

                # Update current candle
                ohlc.update(price, quantity)

                # Broadcast updated OHLC
                ohlc_data = OHLCData(**ohlc.to_dict())
                ohlc_msg = OHLCMessage(
                    type=ResponseType.OHLC_UPDATE,
                    symbol=symbol,
                    timeframe=timeframe.value,
                    ohlc=ohlc_data,
                )
                await self._broadcast_to_set(
                    self._bar_conns[symbol][timeframe], ohlc_msg.model_dump_json()
                )

    async def _listen_to_kafka(self) -> None:
        """Listen to Kafka events and process them"""
        consumer = AsyncKafkaConsumer(KAFKA_INSTRUMENT_EVENTS_TOPIC)

        try:
            await consumer.start()

            async for msg in consumer:
                try:
                    msg_txt = msg.value.decode().strip()
                    event = json.loads(msg_txt)
                    event_type = event.get("type")

                    if event_type == InstrumentEventType.NEW_TRADE:
                        await self._process_trade_event(event)

                    elif event_type == InstrumentEventType.ORDERBOOK_SNAPSHOT:
                        symbol = event["symbol"]
                        if symbol in self._ob_conns and self._ob_conns[symbol]:
                            await self._broadcast_to_set(
                                self._ob_conns[symbol], msg_txt
                            )

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Event processing error: {e}")

        except Exception as e:
            logger.error(f"Kafka listener error: {e}")
        finally:
            await consumer.stop()
