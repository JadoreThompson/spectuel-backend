from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from enums import StrategyType
from models import CustomBaseModel


MODIFY_SENTINEL = "*"


class CommandType(str, Enum):
    NEW_ORDER = "new_order"
    CANCEL_ORDER = "cancel_order"
    MODIFY_ORDER = "modify_order"
    NEW_INSTRUMENT = "new_instrument"


class Command(CustomBaseModel):
    type: CommandType
    data: Any


class NewOrderCommand(CustomBaseModel):
    strategy_type: StrategyType
    instrument_id: str


class NewSingleOrder(NewOrderCommand):
    order: dict


class NewOCOOrder(NewOrderCommand):
    legs: list[dict] = Field(max_length=2)


class NewOTOOrder(NewOrderCommand):
    parent: dict
    child: dict


class NewOTOCOOrder(NewOrderCommand):
    parent: dict
    oco_legs: list[dict] = Field(max_length=2)


class CancelOrderCommand(CustomBaseModel):
    order_id: UUID
    symbol: str


class ModifyOrderCommand(CustomBaseModel):
    order_id: str
    symbol: str
    limit_price: float | None = None
    stop_price: float | None = None


class NewInstrumentCommand(CustomBaseModel):
    instrument_id: str
