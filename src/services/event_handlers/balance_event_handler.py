import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import KAFKA_BALANCE_EVENTS_TOPIC
from db_models import AssetBalances, BalanceEvents, EventLogs, Instruments
from engine.enums import EngineEventCategory
from engine.events import (
    AssetBalanceDecreasedEvent,
    AssetBalanceIncreasedEvent,
    AssetBalanceSnapshotEvent,
    AssetEscrowDecreasedEvent,
    AssetEscrowIncreasedEvent,
    AskSettledEvent,
    BidSettledEvent,
    CashBalanceDecreasedEvent,
    CashBalanceIncreasedEvent,
    CashEscrowDecreasedEvent,
    CashEscrowIncreasedEvent,
)
from engine.events.enums import BalanceEventType
from infra.db import get_db_sess
from infra.kafka import AsyncKafkaConsumer
from .base import BaseEventHandler


class BalanceEventHandler(BaseEventHandler):
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        self._consumer = AsyncKafkaConsumer(KAFKA_BALANCE_EVENTS_TOPIC)

        self._event_classes = {
            BalanceEventType.CASH_BALANCE_INCREASED: CashBalanceIncreasedEvent,
            BalanceEventType.CASH_BALANCE_DECREASED: CashBalanceDecreasedEvent,
            BalanceEventType.CASH_ESCROW_INCREASED: CashEscrowIncreasedEvent,
            BalanceEventType.CASH_ESCROW_DECREASED: CashEscrowDecreasedEvent,
            BalanceEventType.ASSET_BALANCE_INCREASED: AssetBalanceIncreasedEvent,
            BalanceEventType.ASSET_BALANCE_DECREASED: AssetBalanceDecreasedEvent,
            BalanceEventType.ASSET_ESCROW_INCREASED: AssetEscrowIncreasedEvent,
            BalanceEventType.ASSET_ESCROW_DECREASED: AssetEscrowDecreasedEvent,
            BalanceEventType.ASK_SETTLED: AskSettledEvent,
            BalanceEventType.BID_SETTLED: BidSettledEvent,
            BalanceEventType.ASSET_BALANCE_SNAPSHOT: AssetBalanceSnapshotEvent,
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
        event_cls = self._event_classes.get(event_type)

        if not event_cls:
            self._logger.warning(f"No handler for event type: {event_type}")
            return

        self._logger.info(f"Handling {event_type} event")

        try:
            event = event_cls(**event_data)

            async with get_db_sess() as db_sess:
                exists = await db_sess.scalar(
                    select(BalanceEvents).where(
                        BalanceEvents.command_id == event.command_id,
                        BalanceEvents.user_id == event.user_id,
                        BalanceEvents.type == event.type,
                    )
                )

                if exists:
                    self._logger.warning(f"Duplicate event detected - {event}")
                    return

                symbol = getattr(event, "symbol", None)

                db_event = BalanceEvents(
                    event_id=event.id,
                    user_id=event.user_id,
                    command_id=event.command_id,
                    type=event.type,
                    version=event.version,
                    symbol=symbol,
                    payload=event_data,
                    timestamp=event.timestamp,
                )

                db_sess.add(db_event)

                db_event_log = EventLogs(
                    type=EngineEventCategory.BALANCE,
                    event_id=db_event.event_id,
                    timestamp=event.timestamp,
                )
                db_sess.add(db_event_log)

                await self._adjust_asset_balance(event, db_sess)

                await db_sess.commit()

        except ValidationError:
            self._logger.error(
                f"Validation error for event data: {event_data}", exc_info=True
            )
        except Exception:
            self._logger.error("Error processing balance event", exc_info=True)

    async def _adjust_asset_balance(self, event, db_sess: AsyncSession):
        """Adjust asset balance based on event type."""
        if event.type == BalanceEventType.ASSET_BALANCE_INCREASED:
            await self._increase_asset_balance(
                db_sess, event.user_id, event.symbol, event.amount
            )
        elif event.type == BalanceEventType.ASSET_BALANCE_DECREASED:
            await self._decrease_asset_balance(
                db_sess, event.user_id, event.symbol, event.amount
            )
        elif event.type == BalanceEventType.ASSET_ESCROW_INCREASED:
            await self._increase_asset_escrow(
                db_sess, event.user_id, event.symbol, event.amount
            )
        elif event.type == BalanceEventType.ASSET_ESCROW_DECREASED:
            await self._decrease_asset_escrow(
                db_sess, event.user_id, event.symbol, event.amount
            )
        elif event.type == BalanceEventType.ASK_SETTLED:
            await self._increase_asset_balance(
                db_sess,
                event.user_id,
                event.symbol,
                event.asset_balance_increased.amount,
            )
        elif event.type == BalanceEventType.BID_SETTLED:
            await self._increase_asset_balance(
                db_sess,
                event.user_id,
                event.symbol,
                event.asset_balance_increased.amount,
            )

    async def _get_instrument_id(self, db_sess: AsyncSession, symbol: str):
        """Get instrument_id for a given symbol."""
        instrument = await db_sess.scalar(
            select(Instruments).where(Instruments.symbol == symbol)
        )
        if not instrument:
            self._logger.error(f"Instrument not found for symbol: {symbol}")
            return None
        return instrument.instrument_id

    async def _increase_asset_balance(
        self, db_sess: AsyncSession, user_id: str, symbol: str, amount: float
    ):
        """Increase asset balance for a user."""
        instrument_id = await self._get_instrument_id(db_sess, symbol)
        if not instrument_id:
            return

        asset_balance = await db_sess.get(AssetBalances, (instrument_id, user_id))

        if asset_balance:
            asset_balance.balance += amount
        else:
            asset_balance = AssetBalances(
                instrument_id=instrument_id,
                user_id=user_id,
                balance=amount,
            )
            db_sess.add(asset_balance)

    async def _decrease_asset_balance(
        self, db_sess: AsyncSession, user_id: str, symbol: str, amount: float
    ):
        """Decrease asset balance for a user."""
        instrument_id = await self._get_instrument_id(db_sess, symbol)
        if not instrument_id:
            return

        asset_balance = await db_sess.get(AssetBalances, (instrument_id, user_id))

        if asset_balance:
            asset_balance.balance -= amount
        else:
            self._logger.warning(
                f"Asset balance not found for user {user_id}, symbol {symbol}"
            )

    async def _increase_asset_escrow(
        self, db_sess: AsyncSession, user_id: str, symbol: str, amount: float
    ):
        """Increase asset escrow balance for a user."""
        instrument_id = await self._get_instrument_id(db_sess, symbol)
        if not instrument_id:
            return

        asset_balance = await db_sess.get(AssetBalances, (instrument_id, user_id))

        if asset_balance:
            asset_balance.escrow_balance += amount
        else:
            asset_balance = AssetBalances(
                instrument_id=instrument_id,
                user_id=user_id,
                balance=0.0,
                escrow_balance=amount,
            )
            db_sess.add(asset_balance)

    async def _decrease_asset_escrow(
        self, db_sess: AsyncSession, user_id: str, symbol: str, amount: float
    ):
        """Decrease asset escrow balance for a user."""
        instrument_id = await self._get_instrument_id(db_sess, symbol)
        if not instrument_id:
            return

        asset_balance = await db_sess.get(AssetBalances, (instrument_id, user_id))

        if asset_balance:
            asset_balance.escrow_balance -= amount
        else:
            self._logger.warning(
                f"Asset balance not found for user {user_id}, symbol {symbol}"
            )

