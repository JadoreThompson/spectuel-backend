import json
import logging

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import KAFKA_BALANCE_EVENTS_TOPIC
from db_models import BalanceEvents, EventLogs
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
                await db_sess.refresh(db_event)

                db_event_log = EventLogs(
                    type=EngineEventCategory.BALANCE,
                    event_id=db_event.event_id,
                    timestamp=event.timestamp,
                )
                db_sess.add(db_event_log)

                await db_sess.commit()

        except ValidationError:
            self._logger.error(
                f"Validation error for event data: {event_data}", exc_info=True
            )
        except Exception:
            self._logger.error("Error processing balance event", exc_info=True)
