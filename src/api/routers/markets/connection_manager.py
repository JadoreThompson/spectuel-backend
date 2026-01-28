import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

from config import KAFKA_INSTRUMENT_EVENTS_TOPIC
from engine.enums import TimeFrame
from infra.kafka import AsyncKafkaConsumer
from .models import BarSubscription


class ConnectionManager:
    def __init__(self):
        self._bar_conns: dict[str, dict[TimeFrame, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._trade_conns: dict[str, set[WebSocket]] = defaultdict(set)
        self._ob_conns: dict[str, set[WebSocket]] = defaultdict(set)
        self._conn_subscriptions: dict[WebSocket, dict] = {}
        self._closed_connections: asyncio.Queue[WebSocket] = asyncio.Queue()
        self._consumer: AsyncKafkaConsumer | None = None
        self._is_running = False
        self._logger = logging.getLogger("MarketsConnectionManager")

    async def start(self):
        self._is_running = True
        self._consumer = AsyncKafkaConsumer(
            KAFKA_INSTRUMENT_EVENTS_TOPIC,
            group_id="markets_ws_consumer",
            enable_auto_commit=True,
            auto_offset_reset="latest",
        )
        await self._consumer.start()
        asyncio.create_task(self._listen_to_kafka())
        asyncio.create_task(self._cleanup_worker())
        self._logger.info("ConnectionManager started")

    async def stop(self):
        self._is_running = False
        if self._consumer:
            await self._consumer.stop()
        self._logger.info("ConnectionManager stopped")

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._conn_subscriptions[ws] = {
            "orderbooks": [],
            "trades": [],
            "bars": [],
        }

    def disconnect(self, ws: WebSocket):
        self._closed_connections.put_nowait(ws)

    def subscribe(self, ws: WebSocket, request: dict):
        self._unsubscribe_all(ws)

        orderbooks = request.get("orderbooks", [])
        trades = request.get("trades", [])
        bars = request.get("bars", [])

        for symbol in orderbooks:
            self._ob_conns[symbol].add(ws)

        for symbol in trades:
            self._trade_conns[symbol].add(ws)

        for bar_sub in bars:
            symbol = bar_sub.get("symbol")
            timeframes = bar_sub.get("timeframes", [])
            for tf_str in timeframes:
                try:
                    tf = TimeFrame(tf_str)
                    self._bar_conns[symbol][tf].add(ws)
                except ValueError:
                    self._logger.warning(f"Invalid timeframe: {tf_str}")

        self._conn_subscriptions[ws] = {
            "orderbooks": orderbooks,
            "trades": trades,
            "bars": bars,
        }

    def _unsubscribe_all(self, ws: WebSocket):
        for symbol_dict in self._bar_conns.values():
            for tf_set in symbol_dict.values():
                tf_set.discard(ws)

        for trade_set in self._trade_conns.values():
            trade_set.discard(ws)

        for ob_set in self._ob_conns.values():
            ob_set.discard(ws)

    async def _listen_to_kafka(self):
        try:
            async for msg in self._consumer:
                try:
                    event = json.loads(msg.value.decode())
                    event_type = event.get("type")

                    if event_type == "bar_update":
                        await self._handle_bar_update(event)
                    elif event_type == "new_trade":
                        await self._handle_trade(event)
                    elif event_type == "orderbook_snapshot":
                        await self._handle_orderbook_snapshot(event)
                except Exception as e:
                    self._logger.error(f"Error processing event: {e}")
        except Exception as e:
            self._logger.error(f"Kafka consumer error: {e}")

    async def _handle_bar_update(self, event: dict):
        symbol = event.get("symbol")
        timeframe_str = event.get("timeframe")

        if not symbol or not timeframe_str:
            return

        try:
            timeframe = TimeFrame(timeframe_str)
        except ValueError:
            return

        clients = self._bar_conns.get(symbol, {}).get(timeframe, set())
        if clients:
            message = json.dumps(event)
            await self._broadcast_to_set(clients, message)

    async def _handle_trade(self, event: dict):
        symbol = event.get("symbol")
        if not symbol:
            return

        clients = self._trade_conns.get(symbol, set())
        if clients:
            message = json.dumps(event)
            await self._broadcast_to_set(clients, message)

    async def _handle_orderbook_snapshot(self, event: dict):
        symbol = event.get("symbol")
        if not symbol:
            return

        clients = self._ob_conns.get(symbol, set())
        if clients:
            message = json.dumps(event)
            await self._broadcast_to_set(clients, message)

    async def _broadcast_to_set(self, clients: set[WebSocket], message: str):
        clients_snapshot = list(clients)
        tasks = [self._send_to_client(client, message) for client in clients_snapshot]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_to_client(self, client: WebSocket, message: str):
        try:
            await asyncio.wait_for(client.send_text(message), timeout=5.0)
        except asyncio.TimeoutError:
            self._logger.warning("Send timeout, disconnecting client")
            self.disconnect(client)
        except Exception as e:
            self._logger.debug(f"Error sending to client: {e}")
            self.disconnect(client)

    async def _cleanup_worker(self):
        while self._is_running:
            try:
                ws = await asyncio.wait_for(
                    self._closed_connections.get(), timeout=1.0
                )
                self._unsubscribe_all(ws)
                if ws in self._conn_subscriptions:
                    del self._conn_subscriptions[ws]
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._logger.error(f"Cleanup worker error: {e}")


connection_manager = ConnectionManager()
