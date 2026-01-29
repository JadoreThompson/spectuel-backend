from typing import Literal

from engine.enums import TimeFrame
from engine.events import EngineEventBase
from .enums import BarEventType


class BarEventBase(EngineEventBase):
    version: int = 1
    symbol: str
    timeframe: TimeFrame


class BarUpdateEvent(BarEventBase):
    type: Literal[BarEventType.BAR_UPDATE] = BarEventType.BAR_UPDATE
    open: float
    high: float
    low: float
    close: float
    timestamp: int
