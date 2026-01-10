import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import NamedTuple

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import select

from config import KAFKA_ORDER_EVENTS_TOPIC, KAFKA_INSTRUMENT_EVENTS_TOPIC
from db_models import Orders
from engine.enums import InstrumentEventType, Side, LiquidityRole, OrderStatus
from engine.events import (
    NewTradeEvent,
    OrderPlacedEvent,
    OrderCancelledEvent,
    OrderbookSnapshotEvent,
)
from engine.events.enums import OrderEventType
from engine.enums import OrderType
from infra.db import get_db_sess
from infra.kafka import AsyncKafkaConsumer, AsyncKafkaProducer


class OrderInfo(NamedTuple):
    price: float
    side: Side
    remaining_qty: float


class BookState:
    """
    Holds the state and lock for a single instrument.
    This allows granular locking so one active instrument doesn't block others.
    """

    def __init__(self):
        self.lock = asyncio.Lock()
        self.bids: dict[float, float] = defaultdict(float)
        self.asks: dict[float, float] = defaultdict(float)
        self.last_snapshot_ts: float = 0.0


class OrderBookPublisher:
    def __init__(self, snapshot_interval: float = 0.5):
        self._logger = logging.getLogger(type(self).__name__)
        self._snapshot_interval = snapshot_interval

        # State
        self._books: dict[str, BookState] = defaultdict(BookState)
        self._active_orders: dict[str, OrderInfo] = {}
        self._registry_lock = asyncio.Lock()
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None

    async def run(self) -> None:
        await self._rehydrate_state()

        self._consumer = AsyncKafkaConsumer(
            KAFKA_INSTRUMENT_EVENTS_TOPIC,
            KAFKA_ORDER_EVENTS_TOPIC,
            group_id="orderbook_publisher_group",
            auto_offset_reset="latest",
        )
        self._producer = AsyncKafkaProducer()

        await self._consumer.start()
        await self._producer.start()

        self._logger.info("State rehydrated and Kafka connected.")

        try:
            await asyncio.gather(self._consume_loop(), self._snapshot_loop())
        except Exception:
            self._logger.error("An error occurred", exc_info=True)
        finally:
            await self._consumer.stop()
            await self._producer.stop()

    async def _rehydrate_state(self) -> None:
        """
        Query the database for all active orders to rebuild the in-memory book.
        This prevents starting with an empty book after a restart.
        """
        self._logger.info("Rehydrating orderbook state from database...")
        count = 0

        async with get_db_sess() as session:
            stmt = select(Orders).where(
                Orders.status.in_(
                    (OrderStatus.PLACED.value, OrderStatus.PARTIALLY_FILLED.value)
                ),
                Orders.order_type != OrderType.MARKET,
            )
            result = await session.scalars(stmt)

            for order in result:
                remaining_qty = order.quantity - order.executed_quantity

                if remaining_qty > 0:
                    symbol = order.symbol
                    order_id = str(order.order_id)

                    # Ensure book exists
                    if symbol not in self._books:
                        self._books[symbol] = BookState()

                    book = self._books[symbol]
                    price = order.limit_price or order.stop_price
                    if order.side == Side.BID:
                        book.bids[price] += remaining_qty
                    else:
                        book.asks[price] += remaining_qty

                    self._active_orders[order_id] = OrderInfo(
                        price=price, side=Side(order.side), remaining_qty=remaining_qty
                    )

                    count += 1

        self._logger.info(f"Rehydration complete. Loaded {count} active orders.")

    async def _consume_loop(self) -> None:
        async for msg in self._consumer:
            try:
                data = json.loads(msg.value.decode("utf-8"))
                event_type = data.get("type")

                if event_type == OrderEventType.ORDER_PLACED:
                    await self._handle_order_placed(data)
                elif event_type == OrderEventType.ORDER_CANCELLED:
                    await self._handle_order_cancelled(data)
                elif event_type == InstrumentEventType.NEW_TRADE:
                    await self._handle_trade(data)

            except (json.JSONDecodeError, ValueError):
                pass
            except Exception as e:
                self._logger.error(f"Error processing message: {e}", exc_info=True)

    async def _snapshot_loop(self) -> None:
        """
        Periodically iterates active books, grabs their lock, takes a snapshot, and sends it.
        """
        while True:
            start_time = time.time()
            symbols = list(self._books.keys())

            for symbol in symbols:
                book_state = self._books[symbol]

                async with book_state.lock:
                    if (
                        time.time() - book_state.last_snapshot_ts
                        >= self._snapshot_interval
                    ):
                        await self._publish_snapshot(symbol, book_state)
                        book_state.last_snapshot_ts = time.time()

            elapsed = time.time() - start_time
            sleep_time = max(0.1, self._snapshot_interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _publish_snapshot(self, symbol: str, state: BookState) -> None:
        top_bids = sorted(
            [(price, qty) for price, qty in state.bids.items() if qty > 0],
            key=lambda x: x[0],
            reverse=True,
        )[:20]

        top_asks = sorted(
            [(price, qty) for price, qty in state.asks.items() if qty > 0],
            key=lambda x: x[0],
        )[:20]

        snapshot = OrderbookSnapshotEvent(
            version=1, symbol=symbol, bids=top_bids, asks=top_asks
        )

        try:
            await self._producer.send(
                KAFKA_INSTRUMENT_EVENTS_TOPIC,
                snapshot.model_dump_json().encode("utf-8"),
            )
        except Exception as e:
            self._logger.error(f"Failed to emit snapshot for {symbol}: {e}")

    async def _handle_order_placed(self, data: dict) -> None:
        event = OrderPlacedEvent(**data)
        symbol = event.symbol
        order_id = str(event.order_id)

        resting_qty = event.quantity - event.executed_quantity
        if resting_qty <= 0:
            return

        book = self._books[symbol]

        async with book.lock:
            if event.side == Side.BID:
                book.bids[event.price] += resting_qty
            else:
                book.asks[event.price] += resting_qty

            self._active_orders[order_id] = OrderInfo(
                price=event.price, side=event.side, remaining_qty=resting_qty
            )

    async def _handle_order_cancelled(self, data: dict) -> None:
        event = OrderCancelledEvent(**data)
        order_id = str(event.order_id)

        info = self._active_orders.pop(order_id, None)
        if not info:
            return

        book = self._books[event.symbol]

        async with book.lock:
            if info.side == Side.BID:
                self._decrement_level(book.bids, info.price, info.remaining_qty)
            else:
                self._decrement_level(book.asks, info.price, info.remaining_qty)

    async def _handle_trade(self, data: dict) -> None:
        event = NewTradeEvent(**data)

        if event.role == LiquidityRole.MAKER:
            maker_order_id = str(event.order_id)
            info = self._active_orders.get(maker_order_id)

            if info:
                new_qty = info.remaining_qty - event.quantity
                book = self._books[event.symbol]

                async with book.lock:
                    if info.side == Side.BID:
                        self._decrement_level(book.bids, info.price, event.quantity)
                    else:
                        self._decrement_level(book.asks, info.price, event.quantity)

                if new_qty <= 0.00000001:
                    self._active_orders.pop(maker_order_id, None)
                else:
                    self._active_orders[maker_order_id] = OrderInfo(
                        price=info.price, side=info.side, remaining_qty=new_qty
                    )

    def _decrement_level(
        self, level_dict: dict[float, float], price: float, qty: float
    ) -> None:
        if price in level_dict:
            level_dict[price] -= qty
            if level_dict[price] <= 0.00000001:
                del level_dict[price]
