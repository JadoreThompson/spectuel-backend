from typing import Literal
from uuid import UUID

from engine.enums import LiquidityRole, TimeFrame
from engine.events import EngineEventBase
from .enums import InstrumentEventType


class InstrumentEventBase(EngineEventBase):
    version: int = 1
    symbol: str


class InstrumentEngineCreatedEvent(InstrumentEventBase):
    """Emitted when an engine for an instrument has been created"""

    type: Literal[InstrumentEventType.ENGINE_CREATED] = (
        InstrumentEventType.ENGINE_CREATED
    )


class OrderbookSnapshotEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.ORDERBOOK_SNAPSHOT] = (
        InstrumentEventType.ORDERBOOK_SNAPSHOT
    )
    # Format [[price, quantity], [price, quantity]]
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


class NewTradeEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.NEW_TRADE] = InstrumentEventType.NEW_TRADE
    command_id: str
    order_id: UUID
    role: LiquidityRole
    quantity: float
    price: float


class BarUpdateEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.BAR_UPDATE] = InstrumentEventType.BAR_UPDATE
    timeframe: TimeFrame
    open: float
    high: float
    low: float
    close: float
    timestamp: int
