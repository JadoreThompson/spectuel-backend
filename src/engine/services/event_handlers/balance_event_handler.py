import json
import logging
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import KAFKA_BALANCE_EVENTS_TOPIC
from db_models import Users, AssetBalances
from infra.kafka import AsyncKafkaConsumer
from engine.events import (
    CashBalanceIncreasedEvent,
    CashBalanceDecreasedEvent,
    CashEscrowIncreasedEvent,
    CashEscrowDecreasedEvent,
    AssetBalanceIncreasedEvent,
    AssetBalanceDecreasedEvent,
    AssetEscrowIncreasedEvent,
    AssetEscrowDecreasedEvent,
    AskSettledEvent,
    BidSettledEvent,
    AssetBalanceSnapshotEvent,
)
from engine.events.enums import BalanceEventType
from .base import BaseEventHandler


class BalanceEventHandler(BaseEventHandler):
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._consumer = AsyncKafkaConsumer(KAFKA_BALANCE_EVENTS_TOPIC)

        self._handlers = {
            BalanceEventType.CASH_BALANCE_INCREASED: (
                CashBalanceIncreasedEvent,
                self._handle_cash_balance_increased,
            ),
            BalanceEventType.CASH_BALANCE_DECREASED: (
                CashBalanceDecreasedEvent,
                self._handle_cash_balance_decreased,
            ),
            BalanceEventType.CASH_ESCROW_INCREASED: (
                CashEscrowIncreasedEvent,
                self._handle_cash_escrow_increased,
            ),
            BalanceEventType.CASH_ESCROW_DECREASED: (
                CashEscrowDecreasedEvent,
                self._handle_cash_escrow_decreased,
            ),
            BalanceEventType.ASSET_BALANCE_INCREASED: (
                AssetBalanceIncreasedEvent,
                self._handle_asset_balance_increased,
            ),
            BalanceEventType.ASSET_BALANCE_DECREASED: (
                AssetBalanceDecreasedEvent,
                self._handle_asset_balance_decreased,
            ),
            BalanceEventType.ASSET_ESCROW_INCREASED: (
                AssetEscrowIncreasedEvent,
                self._handle_asset_escrow_increased,
            ),
            BalanceEventType.ASSET_ESCROW_DECREASED: (
                AssetEscrowDecreasedEvent,
                self._handle_asset_escrow_decreased,
            ),
            BalanceEventType.ASK_SETTLED: (
                AskSettledEvent,
                self._handle_ask_settled,
            ),
            BalanceEventType.BID_SETTLED: (
                BidSettledEvent,
                self._handle_bid_settled,
            ),
            BalanceEventType.ASSET_BALANCE_SNAPSHOT: (
                AssetBalanceSnapshotEvent,
                self._handle_asset_balance_snapshot,
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
        """Process a single balance event within an isolated DB session."""
        event_type = event_data.get("type")
        handler_data = self._handlers.get(event_type)
        if not handler_data:
            self._logger.warning(f"No handler for event type: {event_type}")
            return

        event_cls, handler = handler_data

        self._logger.info(f"Handling {event_type} event")

        try:
            async with self._log_event(event_data, event_cls) as (db_sess, _, event):
                await handler(event, db_sess)

        except ValidationError:
            self._logger.error(
                f"Validation error for event data: {event_data}", exc_info=True
            )
        except Exception:
            self._logger.error(f"Error processing balance event", exc_info=True)

    async def _get_user(self, db_sess: AsyncSession, user_id: UUID) -> Users:
        """Helper to fetch a user record."""
        return await db_sess.get(Users, user_id)

    async def _get_asset_balance(
        self, db_sess: AsyncSession, user_id: UUID, symbol: str
    ) -> AssetBalances:
        """Helper to fetch an asset balance record."""
        stmt = select(AssetBalances).where(
            AssetBalances.user_id == user_id, AssetBalances.symbol == symbol
        )
        result = await db_sess.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_asset_balance(
        self, db_sess: AsyncSession, user_id: UUID, symbol: str
    ) -> AssetBalances:
        """Helper to fetch or create an asset balance record."""
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

    async def _handle_cash_balance_increased(
        self, event: CashBalanceIncreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle cash balance increase."""
        user = await self._get_user(db_sess, UUID(event.user_id))
        if not user:
            self._logger.error(f"User '{event.user_id}' not found")
            return

        user.cash_balance += event.amount
        db_sess.add(user)

    async def _handle_cash_balance_decreased(
        self, event: CashBalanceDecreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle cash balance decrease."""
        user = await self._get_user(db_sess, UUID(event.user_id))
        if not user:
            self._logger.error(f"User '{event.user_id}' not found")
            return

        user.cash_balance -= event.amount
        db_sess.add(user)

    async def _handle_cash_escrow_increased(
        self, event: CashEscrowIncreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle cash escrow increase."""
        user = await self._get_user(db_sess, UUID(event.user_id))
        if not user:
            self._logger.error(f"User '{event.user_id}' not found")
            return

        user.escrow_balance += event.amount
        db_sess.add(user)

    async def _handle_cash_escrow_decreased(
        self, event: CashEscrowDecreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle cash escrow decrease."""
        user = await self._get_user(db_sess, UUID(event.user_id))
        if not user:
            self._logger.error(f"User '{event.user_id}' not found")
            return

        user.escrow_balance -= event.amount
        db_sess.add(user)

    async def _handle_asset_balance_increased(
        self, event: AssetBalanceIncreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle asset balance increase."""
        asset_balance = await self._ensure_asset_balance(
            db_sess, UUID(event.user_id), event.symbol
        )
        asset_balance.balance += event.amount
        db_sess.add(asset_balance)

    async def _handle_asset_balance_decreased(
        self, event: AssetBalanceDecreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle asset balance decrease."""
        asset_balance = await self._get_asset_balance(
            db_sess, UUID(event.user_id), event.symbol
        )
        if not asset_balance:
            self._logger.error(
                f"Asset balance not found for user '{event.user_id}', symbol '{event.symbol}'"
            )
            return

        asset_balance.balance -= event.amount
        db_sess.add(asset_balance)

    async def _handle_asset_escrow_increased(
        self, event: AssetEscrowIncreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle asset escrow increase."""
        asset_balance = await self._ensure_asset_balance(
            db_sess, UUID(event.user_id), event.symbol
        )
        asset_balance.escrow_balance += event.amount
        db_sess.add(asset_balance)

    async def _handle_asset_escrow_decreased(
        self, event: AssetEscrowDecreasedEvent, db_sess: AsyncSession
    ) -> None:
        """Handle asset escrow decrease."""
        asset_balance = await self._get_asset_balance(
            db_sess, UUID(event.user_id), event.symbol
        )
        if not asset_balance:
            self._logger.error(
                f"Asset balance not found for user '{event.user_id}', symbol '{event.symbol}'"
            )
            return

        asset_balance.escrow_balance -= event.amount
        db_sess.add(asset_balance)

    async def _handle_ask_settled(
        self, event: AskSettledEvent, db_sess: AsyncSession
    ) -> None:
        """
        Handle ask order settlement.
        Processes the nested events for escrow, balance, and cash updates.
        """
        await self._handle_asset_escrow_decreased(event.asset_escrow_decreased, db_sess)
        await self._handle_asset_balance_decreased(
            event.asset_balance_decreased, db_sess
        )
        await self._handle_cash_balance_increased(event.cash_balance_increased, db_sess)

    async def _handle_bid_settled(
        self, event: BidSettledEvent, db_sess: AsyncSession
    ) -> None:
        """
        Handle bid order settlement.
        Processes the nested events for cash escrow, balance, and asset updates.
        """
        await self._handle_cash_escrow_decreased(event.cash_escrow_decreased, db_sess)
        await self._handle_cash_balance_decreased(event.cash_balance_decreased, db_sess)
        await self._handle_asset_balance_increased(
            event.asset_balance_increased, db_sess
        )

    async def _handle_asset_balance_snapshot(
        self, event: AssetBalanceSnapshotEvent, db_sess: AsyncSession
    ) -> None:
        self._logger.info(
            f"Asset balance snapshot for user '{event.user_id}', "
            f"symbol '{event.symbol}': "
            f"asset={event.available_asset_balance}, "
            f"cash={event.available_cash_balance}"
        )
