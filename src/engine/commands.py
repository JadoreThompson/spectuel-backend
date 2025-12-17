import time
from typing import Any, Literal, Union, TypeAlias
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from models import CustomBaseModel
from .enums import CommandType, OrderType, Side, StrategyType


class CommandBase(CustomBaseModel):
    id: UUID = Field(default_factory=uuid4)
    version: int = 1
    details: dict[str, Any] | None = None
    timestamp: int = Field(default_factory=lambda: int(time.time()))


class NewOrderCommandBase(CommandBase):
    type: Literal[CommandType.NEW_ORDER] = CommandType.NEW_ORDER
    strategy_type: StrategyType
    symbol: str


class SingleOrderMeta(CustomBaseModel):
    order_id: UUID
    user_id: UUID
    order_type: OrderType
    side: Side
    quantity: float = Field(gt=0.0)
    limit_price: float | None = Field(None, gt=0.0)
    stop_price: float | None = Field(None, gt=0.0)

    @field_validator("quantity", mode='after')
    def validate_quantity(cls, v):
        v = round(v, 2)
        if v:
            return v
        raise ValueError("Quantity needs to be greater than 0")

    def model_post_init(self, context):
        if self.limit_price is None and self.order_type == OrderType.LIMIT:
            raise ValueError("Limit price must be specified")
        if self.stop_price is None and self.order_type == OrderType.STOP:
            raise ValueError("Stop price must be specified")
        return self


class NewSingleOrderCommand(NewOrderCommandBase, SingleOrderMeta):
    pass


class NewOCOOrderCommand(NewOrderCommandBase):
    legs: list[SingleOrderMeta] = Field(max_length=2)


class NewOTOOrderCommand(NewOrderCommandBase):
    parent: dict
    child: dict


class NewOTOCOOrderCommand(NewOrderCommandBase):
    parent: dict
    oco_legs: list[SingleOrderMeta] = Field(min_length=2, max_length=2)


class CancelOrderCommand(CommandBase):
    type: Literal[CommandType.CANCEL_ORDER] = CommandType.CANCEL_ORDER
    order_id: UUID
    symbol: str


class ModifyOrderCommand(CommandBase):
    type: Literal[CommandType.MODIFY_ORDER] = CommandType.MODIFY_ORDER
    order_id: str
    limit_price: float | None = Field(None, gt=0.0)
    stop_price: float | None = Field(None, gt=0.0)


class NewInstrumentCommand(CommandBase):
    type: Literal[CommandType.NEW_INSTRUMENT] = CommandType.NEW_INSTRUMENT
    symbol: str
    price: float


CommandT: TypeAlias = Union[
    NewSingleOrderCommand,
    NewOCOOrderCommand,
    NewOTOOrderCommand,
    NewOTOCOOrderCommand,
    CancelOrderCommand,
    ModifyOrderCommand,
]
