import json
import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import KAFKA_ORDER_EVENTS_TOPIC
from db_models import EventLogs, OrderEvents, Orders
from engine.enums import EngineEventCategory, OrderStatus
from engine.events import (
    OrderCancelledEvent,
    OrderFilledEvent,
    OrderModifiedEvent,
    OrderModifyRejectedEvent,
    OrderPartiallyFilledEvent,
    OrderPlacedEvent,
)
from engine.events.enums import OrderEventType
from infra.db import get_db_sess
from infra.kafka import AsyncKafkaConsumer
from .base import BaseEventHandler


class OrderEventHandler(BaseEventHandler):
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._consumer = AsyncKafkaConsumer(KAFKA_ORDER_EVENTS_TOPIC)

        self._handlers = {
            OrderEventType.ORDER_PLACED: (
                OrderPlacedEvent,
                self._handle_order_placed,
            ),
            OrderEventType.ORDER_PARTIALLY_FILLED: (
                OrderPartiallyFilledEvent,
                self._handle_order_partially_filled,
            ),
            OrderEventType.ORDER_FILLED: (
                OrderFilledEvent,
                self._handle_order_filled,
            ),
            OrderEventType.ORDER_MODIFIED: (
                OrderModifiedEvent,
                self._handle_order_modified,
            ),
            OrderEventType.ORDER_MODIFY_REJECTED: (
                OrderModifyRejectedEvent,
                self._handle_order_modify_rejected,
            ),
            OrderEventType.ORDER_CANCELLED: (
                OrderCancelledEvent,
                self._handle_order_cancelled,
            ),
        }

    async def run(self):
        try:
            await self._consumer.start()
            async for message in self._consumer:
                event_data = json.loads(message.value.decode())
                await self.handle_event(event_data)
        finally:
            await self._consumer.stop()

    async def handle_event(self, event_data: dict):
        """Process a single order event within an isolated DB session."""
        event_type = event_data.get("type")
        handler_data = self._handlers.get(event_type)
        if not handler_data:
            self._logger.warning(f"No handler for event type: {event_type}")
            return

        event_cls, handler = handler_data
        self._logger.info(f"Handling {event_type} event")

        try:
            event = event_cls(**event_data)

            async with get_db_sess() as db_sess:
                exists = await db_sess.scalar(
                    select(OrderEvents).where(
                        OrderEvents.command_id == event.command_id,
                        OrderEvents.order_id == event.order_id,
                        OrderEvents.type == event.type,
                    )
                )

                if exists:
                    self._logger.warning(f"Duplicate event detected - {event}")
                    return

                symbol = getattr(event, "symbol", None)
                if not symbol:
                    order = await self._get_order(db_sess, event.order_id)
                    if order:
                        symbol = order.symbol
                    else:
                        self._logger.error(
                            f"Cannot determine symbol for event {event.id}, order not found"
                        )
                        return

                user_id = None
                order = await self._get_order(db_sess, event.order_id)
                if order:
                    user_id = order.user_id
                else:
                    self._logger.error(
                        f"Cannot determine user_id for event {event.id}, order not found"
                    )
                    return

                db_event = OrderEvents(
                    event_id=event.id,
                    type=event.type,
                    order_id=event.order_id,
                    user_id=user_id,
                    command_id=event.command_id,
                    version=event.version,
                    symbol=symbol,
                    payload=event_data,
                    timestamp=event.timestamp,
                )

                db_sess.add(db_event)
                # await db_sess.refresh(db_event)
                # db_sess.flush

                db_event_log = EventLogs(
                    type=EngineEventCategory.ORDER,
                    event_id=db_event.event_id,
                    timestamp=event.timestamp,
                )
                db_sess.add(db_event_log)

                await handler(event, db_sess)
                print('done')

                await db_sess.commit()

        except ValidationError:
            self._logger.error(
                f"Validation error for event data: {event_data}", exc_info=True
            )
        except Exception:
            self._logger.error("Error processing order event", exc_info=True)

    async def _get_order(self, db_sess: AsyncSession, order_id: UUID) -> Orders | None:
        """Helper to fetch an order record."""
        return await db_sess.get(Orders, order_id)

    async def _handle_order_placed(
        self, event: OrderPlacedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle order placed event by updating its status."""
        order = await self._get_order(db_sess, event.order_id)
        if not order:
            self._logger.error(f"Order '{event.order_id}' not found for PLACED event")
            return

        order.status = OrderStatus.PLACED
        db_sess.add(order)

    async def _handle_order_partially_filled(
        self, event: OrderPartiallyFilledEvent, db_sess: AsyncSession
    ) -> None:
        """Handle order partially filled event."""
        order = await self._get_order(db_sess, event.order_id)
        if not order:
            self._logger.error(
                f"Order '{event.order_id}' not found for PARTIALLY_FILLED event"
            )
            return

        order.executed_quantity = event.executed_quantity
        order.status = OrderStatus.PARTIALLY_FILLED
        db_sess.add(order)

    async def _handle_order_filled(
        self, event: OrderFilledEvent, db_sess: AsyncSession
    ) -> None:
        """Handle order filled event."""
        order = await self._get_order(db_sess, event.order_id)
        if not order:
            self._logger.error(f"Order '{event.order_id}' not found for FILLED event")
            return

        order.executed_quantity = event.order['executed_quantity']
        order.status = OrderStatus.FILLED
        db_sess.add(order)

    async def _handle_order_modified(
        self, event: OrderModifiedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle order modified event."""
        order = await self._get_order(db_sess, event.order_id)
        if not order:
            self._logger.error(f"Order '{event.order_id}' not found for MODIFIED event")
            return

        if event.limit_price is not None:
            order.limit_price = event.limit_price
        if event.stop_price is not None:
            order.stop_price = event.stop_price

        db_sess.add(order)

    async def _handle_order_modify_rejected(
        self, event: OrderModifyRejectedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle order modify rejected event."""
        self._logger.warning(
            f"Order modification for order '{event.order_id}' rejected. "
            f"Reason: {event.reason}"
        )

    async def _handle_order_cancelled(
        self, event: OrderCancelledEvent, db_sess: AsyncSession
    ) -> None:
        """Handle order cancelled event."""
        order = await self._get_order(db_sess, event.order_id)
        if not order:
            self._logger.error(
                f"Order '{event.order_id}' not found for CANCELLED event"
            )
            return

        order.status = OrderStatus.CANCELLED
        db_sess.add(order)
