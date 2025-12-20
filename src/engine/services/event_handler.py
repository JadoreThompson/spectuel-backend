import json
import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_INSTRUMENT_EVENTS_TOPIC,
    KAFKA_ORDER_EVENTS_TOPIC,
    KAFKA_TRADE_EVENTS_TOPIC,
)
from db_models import (
    EventLogs,
    Orders,
    Trades,
    Users,
    Transactions,
    AssetBalances,
)
from engine.config import SYSTEM_USER_ID
from engine.enums import TransactionType, Side, OrderType, OrderStatus
from engine.events import (
    OrderPlacedEvent,
    OrderPartiallyFilledEvent,
    OrderFilledEvent,
    OrderModifiedEvent,
    OrderCancelledEvent,
    NewTradeEvent,
    AssetBalanceSnapshotEvent,
    InstrumentPriceEvent,
)
from engine.events.enums import OrderEventType, TradeEventType
from engine.services.balance_manager import BalanceManager
from infra.db import get_db_sess


class EventHandler:
    """
    Processes events emitted by the matching engine asynchronously.
    Ensures strict accounting lifecycles for Assets and Cash.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

        self._handlers = {
            OrderEventType.ORDER_PLACED: (
                OrderPlacedEvent,
                lambda event, db_sess: self._handle_order_status_update(
                    event.order_id, OrderStatus.PLACED, db_sess
                ),
            ),
            OrderEventType.ORDER_PARTIALLY_FILLED: (
                OrderPartiallyFilledEvent,
                lambda event, db_sess: self._handle_order_status_update(
                    event.order_id, OrderStatus.PARTIALLY_FILLED, db_sess
                ),
            ),
            OrderEventType.ORDER_FILLED: (
                OrderFilledEvent,
                lambda event, db_sess: self._handle_order_status_update(
                    event.order_id, OrderStatus.FILLED, db_sess
                ),
            ),
            OrderEventType.ORDER_CANCELLED: (
                OrderCancelledEvent,
                self._handle_order_cancelled,
            ),
            OrderEventType.ORDER_MODIFIED: (
                OrderModifiedEvent,
                self._handle_order_modified,
            ),
            TradeEventType.NEW_TRADE: (NewTradeEvent, self._handle_new_trade),
        }

        self._bm = BalanceManager()

    async def run(self):
        """Main async loop."""
        self._consumer = AIOKafkaConsumer(
            KAFKA_BALANCE_EVENTS_TOPIC,
            KAFKA_ORDER_EVENTS_TOPIC,
            KAFKA_TRADE_EVENTS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset="earliest",
            group_id="event_handler_group",
        )
        self._producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        await self._consumer.start()
        await self._producer.start()

        try:
            async for msg in self._consumer:
                event_data = msg.value.decode()
                headers = dict(msg.headers or ())
                if "user_id" in headers and headers["user_id"] == SYSTEM_USER_ID:
                    continue

                await self.process_event(json.loads(event_data))
        except Exception as e:
            self._logger.error(f"Critical consumer error: {e}")
        finally:
            await self._consumer.stop()
            await self._producer.stop()

    async def process_event(self, event_data: dict) -> None:
        """
        Process a single event within an isolated DB db_sess.
        """
        data = self._handlers.get(event_data.get("type"))
        if not data:
            return

        event_cls, handler = data

        try:
            event = event_cls(**event_data)
        except ValidationError as e:
            self._logger.error(f"Failed to parse event: {e}")
            return

        try:
            async with get_db_sess() as db_sess:
                db_event_log = EventLogs(
                    event_id=event.id,
                    event_type=event.type,
                    data=event_data,
                    timestamp=event.timestamp,
                )
                db_sess.add(db_event_log)

                await handler(event, db_sess)

                if event.type == TradeEventType.NEW_TRADE:
                    order = await db_sess.get(Orders, event.order_id)
                    if order:
                        asset_bal = await self._bm.get_available_asset_balance_async(
                            order.user_id, order.symbol
                        )
                        cash_bal = await self._bm.get_available_cash_balance_async(
                            order.user_id
                        )

                        snapshot_event = AssetBalanceSnapshotEvent(
                            version=1,
                            symbol=str(order.symbol),
                            user_id=str(order.user_id),
                            available_cash_balance=float(cash_bal),
                            available_asset_balance=float(asset_bal),
                        )

                        await self._producer.send_and_wait(
                            KAFKA_ORDER_EVENTS_TOPIC,
                            snapshot_event.model_dump_json().encode(),
                        )

                await db_sess.commit()

        except Exception as e:
            self._logger.error(
                f"Error processing event id='{event.id}', type='{event.type}': {e}",
                exc_info=True,
            )

    async def _get_asset_balance(
        self, db_sess: AsyncSession, user_id: UUID, symbol: str
    ) -> AssetBalances:
        """Helper to fetch an asset balance record."""
        stmt = select(AssetBalances).where(
            AssetBalances.user_id == user_id,
            AssetBalances.symbol == symbol,
        )
        result = await db_sess.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_asset_balance(
        self, db_sess: AsyncSession, user_id: UUID, symbol: str
    ) -> AssetBalances:
        """Helper to fetch or create an asset balance record (for Buyers)."""
        asset_balance = await self._get_asset_balance(db_sess, user_id, symbol)
        if not asset_balance:
            asset_balance = AssetBalances(
                user_id=user_id,
                symbol=symbol,
                balance=0.0,
                escrow_balance=0.0,
            )
            db_sess.add(asset_balance)
        return asset_balance

    async def _handle_order_status_update(
        self, order_id: UUID, status: OrderStatus, db_sess: AsyncSession
    ):
        order = await db_sess.get(Orders, order_id)
        if not order:
            return

        order.status = status
        db_sess.add(order)

    async def _handle_order_cancelled(
        self, event: OrderCancelledEvent, db_sess: AsyncSession
    ) -> None:
        """
        Handles cancellations by refunding escrowed funds or assets.
        Logic: Move funds from Escrow -> Available.
        """
        order = await db_sess.get(Orders, event.order_id)
        if not order:
            return

        if order.status == OrderStatus.CANCELLED.value:
            return

        order.status = OrderStatus.CANCELLED.value
        user = await db_sess.get(Users, order.user_id)
        if not user:
            return

        # Calculate remaining quantity to refund
        unfilled_qty = order.quantity - order.executed_quantity

        if unfilled_qty <= 0:
            db_sess.add(order)
            return

        if order.side == Side.BID.value:
            # BID Refund: Return Cash from Escrow to Available
            lock_price = self._get_lock_price(order)
            refund_amount = lock_price * unfilled_qty

            user.escrow_balance -= refund_amount
            user.cash_balance += refund_amount

            refund_tx = Transactions(
                user_id=user.user_id,
                amount=refund_amount,
                transaction_type=TransactionType.ESCROW.value,
                related_id=str(order.order_id),
                balance=user.cash_balance,
            )
            db_sess.add(refund_tx)
            db_sess.add(user)

        elif order.side == Side.ASK.value:
            # ASK Refund: Return Asset from Escrow to Available
            asset_balance = await self._ensure_asset_balance(
                db_sess, user.user_id, order.symbol
            )
            asset_balance.escrow_balance -= unfilled_qty
            asset_balance.balance += unfilled_qty
            db_sess.add(asset_balance)

        db_sess.add(order)

    async def _handle_order_modified(
        self, event: OrderModifiedEvent, db_sess: AsyncSession
    ) -> None:
        """
        Handles order modifications.
        Crucial: Updates Escrow requirements if price changes.
        """
        order = await db_sess.get(Orders, event.order_id)
        if not order:
            return

        user = await db_sess.get(Users, order.user_id)
        if not user:
            return

        new_price_val = (
            event.details.get("price") or event.limit_price or event.stop_price
        )

        if new_price_val is not None and order.side == Side.BID.value:
            old_lock_price = Decimal(str(self._get_lock_price(order)))
            new_lock_price = Decimal(str(new_price_val))

            remaining_qty = Decimal(str(order.quantity)) - Decimal(
                str(order.executed_quantity)
            )

            # If price increases, we need to lock more (Cash -> Escrow)
            # If price decreases, we refund (Escrow -> Cash)
            diff_per_unit = new_lock_price - old_lock_price
            total_diff = diff_per_unit * remaining_qty

            user.escrow_balance = float(Decimal(str(user.escrow_balance)) + total_diff)
            user.cash_balance = float(Decimal(str(user.cash_balance)) - total_diff)
            db_sess.add(user)

        # Update Order Record
        if new_price_val is not None:
            if order.order_type == OrderType.LIMIT.value:
                order.limit_price = new_price_val
            elif order.order_type == OrderType.STOP.value:
                order.stop_price = new_price_val
            db_sess.add(order)

    async def _handle_new_trade(
        self, event: NewTradeEvent, db_sess: AsyncSession
    ) -> None:
        """
        Handles Trade Execution.
        Performs full double-entry accounting updates for Cash and Assets.
        """
        order = await db_sess.get(Orders, event.order_id)
        if order is None:
            self._logger.error(f"Order '{event.order_id}' doesn't exist.")
            return

        user = await db_sess.get(Users, order.user_id)
        if user is None:
            self._logger.error(f"User for Order '{event.order_id}' doesn't exist.")
            return

        trade_price = event.price
        trade_quantity = event.quantity
        trade_value = trade_price * trade_quantity

        new_trade = Trades(
            order_id=order.order_id,
            user_id=user.user_id,
            symbol=order.symbol,
            price=event.price,
            quantity=trade_quantity,
            role=event.role.value,
            executed_at=datetime.fromtimestamp(event.timestamp),
        )
        db_sess.add(new_trade)
        await db_sess.flush()  # Flush to generate trade_id

        # Update Order Stats
        prev_exec_qty = order.executed_quantity
        prev_avg_filled_price = order.avg_fill_price or 0.0

        new_exec_qty = prev_exec_qty + trade_quantity
        new_avg_price = (
            (prev_avg_filled_price * prev_exec_qty) + trade_value
        ) / new_exec_qty

        order.executed_quantity = new_exec_qty
        order.avg_fill_price = new_avg_price

        if order.side == Side.BID.value:
            # surplus = trade_value - ()  # In case order crossed the spread
            lock_price = self._get_lock_price(order)
            surplus = trade_value - (lock_price * trade_quantity)

            # user.escrow_balance = float(
            #     Decimal(str(user.escrow_balance)) - escrow_release_amount
            # )
            user.escrow_balance -= trade_value
            # user.cash_balance = float(Decimal(str(user.cash_balance)) + surplus)
            user.cash_balance -= trade_value + surplus

            asset_balance = await self._ensure_asset_balance(
                db_sess, user.user_id, order.symbol
            )
            # Available balance increases by trade quantity
            # asset_balance.balance = float(
            #     Decimal(str(asset_balance.balance)) + trade_quantity
            # )
            asset_balance += trade_quantity
            db_sess.add(asset_balance)

            new_transaction = Transactions(
                user_id=user.user_id,
                amount=-trade_value,
                transaction_type=TransactionType.TRADE.value,
                related_id=str(new_trade.trade_id),
                balance=user.cash_balance,
            )

        else:  # ASK order
            asset_balance = await self._ensure_asset_balance(
                db_sess, user.user_id, order.symbol
            )

            # asset_balance.escrow_balance = float(
            #     Decimal(str(asset_balance.escrow_balance)) - trade_quantity
            # )
            asset_balance.escrow_balance -= trade_quantity
            asset_balance.balance -= trade_quantity
            db_sess.add(asset_balance)

            # revenue = trade_value
            # user.cash_balance = float(Decimal(str(user.cash_balance)) + revenue)
            user.cash_balance += trade_value

            new_transaction = Transactions(
                user_id=user.user_id,
                amount=trade_value,
                transaction_type=TransactionType.TRADE.value,
                related_id=str(new_trade.trade_id),
                balance=user.cash_balance,
            )

        db_sess.add(order)
        db_sess.add(user)
        db_sess.add(new_transaction)

        # Emit public price event
        price_event = InstrumentPriceEvent(
            symbol=order.symbol,
            price=event.price,
            timestamp=event.timestamp,
        )

        await self._producer.send_and_wait(
            KAFKA_INSTRUMENT_EVENTS_TOPIC, price_event.model_dump_json().encode()
        )

    def _get_lock_price(self, order: Orders) -> float:
        """
        Determines the price used to lock funds/calculate refunds.
        For Market orders, implies the Engine locked based on a logic not shown here,
        but for standard accounting we fallback to avg_fill or estimated entry.
        """
        if order.order_type == OrderType.LIMIT.value and order.limit_price:
            return order.limit_price
        if order.order_type == OrderType.STOP.value and order.stop_price:
            return order.stop_price
        raise NotImplementedError(f"Lock price for {order.order_type} not implemented")
