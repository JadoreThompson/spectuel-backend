from typing import Literal
from uuid import UUID

from engine.enums import LiquidityRole
from engine.events import EngineEventBase
from .enums import TradeEventType


class NewTradeEvent(EngineEventBase):
    type: Literal[TradeEventType.NEW_TRADE] = TradeEventType.NEW_TRADE
    version: int = 1
    order_id: UUID
    symbol: str
    role: LiquidityRole
    quantity: float
    price: float
