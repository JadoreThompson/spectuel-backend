import json
import logging
import threading
import time
from collections import defaultdict
from typing import Any, NamedTuple

from kafka import KafkaConsumer, KafkaProducer
from spectuel_engine_utils.enums import Side, LiquidityRole
from spectuel_engine_utils.events import (
    NewTradeEvent,
    OrderPlacedEvent,
    OrderCancelledEvent,
    OrderbookSnapshotEvent
)
from spectuel_engine_utils.events.enums import TradeEventType, OrderEventType

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_TRADE_EVENTS_TOPIC,
    KAFKA_ORDER_EVENTS_TOPIC,
    KAFKA_INSTRUMENT_EVENTS_TOPIC,
)
from .base import RunnerBase


class OrderInfo(NamedTuple):
    price: float
    side: Side
    remaining_qty: float


class OrderBookSnapshotRunner(RunnerBase):
    def __init__(self, snapshot_interval: float = 0.5):
        self._snapshot_interval = snapshot_interval
        self._lock = threading.Lock()
        self._books: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "bids": defaultdict(float),
                "asks": defaultdict(float),
            }
        )

        self._active_orders: dict[str, OrderInfo] = {}

        self._consumer = KafkaConsumer(
            KAFKA_TRADE_EVENTS_TOPIC,
            KAFKA_ORDER_EVENTS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id="orderbook_snapshotter_v1",
            auto_offset_reset="latest",
        )
        self._producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)

        # Background Snapshot Thread
        self._running = True
        self._snapshot_thread = threading.Thread(
            target=self._snapshot_loop,
            name=f"{self.__class__.__name__}Thread",
            daemon=True,
        )

        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self) -> None:
        self._logger.info("OrderBook Snapshot Runner started.")
        self._snapshot_thread.start()

        try:
            for msg in self._consumer:
                try:
                    data = json.loads(msg.value.decode("utf-8"))
                    event_type = data.get("type")

                    with self._lock:
                        if event_type == OrderEventType.ORDER_PLACED:
                            self._handle_order_placed(data)
                        elif event_type == OrderEventType.ORDER_CANCELLED:
                            self._handle_order_cancelled(data)
                        elif event_type == TradeEventType.NEW_TRADE:
                            self._handle_trade(data)

                except (json.JSONDecodeError, ValueError):
                    pass
                except Exception as e:
                    self._logger.error(f"Error processing message: {e}", exc_info=True)
        finally:
            self._running = False
            self._snapshot_thread.join(timeout=2.0)

    def _snapshot_loop(self) -> None:
        """Background thread to emit snapshots every 0.5s."""
        while self._running:
            start_time = time.time()
            try:
                self._emit_snapshots()
            except Exception as e:
                self._logger.error(f"Error in snapshot loop: {e}", exc_info=True)

            # Sleep remainder of interval
            elapsed = time.time() - start_time
            sleep_time = max(0.0, self._snapshot_interval - elapsed)
            if sleep_time:
                time.sleep(sleep_time)

    def _emit_snapshots(self) -> None:
        with self._lock:
            for instrument_id, book in self._books.items():
                self._publish_snapshot(instrument_id, book)

    def _publish_snapshot(self, instrument_id: str, book: dict) -> None:
        top_bids = dict(
            sorted(book["bids"].items(), key=lambda x: x[0], reverse=True)[:5]
        )

        top_asks = dict(
            sorted(book["asks"].items(), key=lambda x: x[0], reverse=False)[:5]
        )

        snapshot = OrderbookSnapshotEvent(
            instrument_id=instrument_id, bids=top_bids, asks=top_asks
        )

        try:
            self._producer.send(
                KAFKA_INSTRUMENT_EVENTS_TOPIC,
                snapshot.model_dump_json().encode("utf-8"),
            )
        except Exception as e:
            self._logger.error(f"Failed to emit snapshot for {instrument_id}: {e}")

    def _handle_order_placed(self, data: dict) -> None:
        event = OrderPlacedEvent(**data)
        inst_id = str(event.instrument_id)
        order_id = str(event.order_id)
        book = self._books[inst_id]

        resting_qty = event.quantity - event.executed_quantity

        if resting_qty > 0:
            if event.side == Side.BID:
                book["bids"][event.price] += resting_qty
            else:
                book["asks"][event.price] += resting_qty

            self._active_orders[order_id] = OrderInfo(
                price=event.price, side=event.side, remaining_qty=resting_qty
            )

    def _handle_order_cancelled(self, data: dict) -> None:
        event = OrderCancelledEvent(**data)
        order_id = str(event.order_id)

        order_info = self._active_orders.get(order_id)
        if not order_info:
            return

        inst_id = str(event.instrument_id)
        book = self._books[inst_id]

        if order_info.side == Side.BID:
            self._decrement_level(
                book["bids"], order_info.price, order_info.remaining_qty
            )
        else:
            self._decrement_level(
                book["asks"], order_info.price, order_info.remaining_qty
            )

        del self._active_orders[order_id]

    def _handle_trade(self, data: dict) -> None:
        event = NewTradeEvent(**data)
        inst_id = str(event.instrument_id)

        if event.role == LiquidityRole.MAKER:
            maker_order_id = str(event.order_id)

            if maker_order_id in self._active_orders:
                info = self._active_orders[maker_order_id]
                new_qty = info.remaining_qty - event.quantity

                book = self._books[inst_id]
                if info.side == Side.BID:
                    self._decrement_level(book["bids"], info.price, event.quantity)
                else:
                    self._decrement_level(book["asks"], info.price, event.quantity)

                self._active_orders[maker_order_id] = OrderInfo(
                    price=info.price, side=info.side, remaining_qty=new_qty
                )

    def _decrement_level(self, level_dict: dict, price: float, qty: float) -> None:
        if price in level_dict:
            level_dict[price] -= qty
            level_dict.pop(price)
