from typing import Literal

# from spectuel_engine_utils.events.base import EngineEventBase
from engine.events import EngineEventBase
from .enums import InstrumentEventType


class InstrumentEventBase(EngineEventBase):
    version: int = 1
    symbol: str


class NewInstrumentEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.NEW_INSTRUMENT] = (
        InstrumentEventType.NEW_INSTRUMENT
    )


class InstrumentPriceEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.PRICE] = InstrumentEventType.PRICE
    price: float


class InstrumentHeartbeatEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.HEARTBEAT] = InstrumentEventType.HEARTBEAT
    status: Literal["alive", "dead"]


class OrderbookSnapshotEvent(InstrumentEventBase):
    type: Literal[InstrumentEventType.ORDERBOOK_SNAPSHOT] = (
        InstrumentEventType.ORDERBOOK_SNAPSHOT
    )
    # Format [[price, quantity], [price, quantity]]
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]
