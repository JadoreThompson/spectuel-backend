from enum import Enum
from typing import Literal

from models import CustomBaseModel


class TradeEventType(str, Enum):
    NEW_TRADE = "new"


class NewTradeEvent(CustomBaseModel):
    type: Literal[TradeEventType.NEW_TRADE] = TradeEventType.NEW_TRADE
