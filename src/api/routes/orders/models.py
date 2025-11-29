from datetime import datetime
from typing import TypeAlias, Union
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from spectuel_engine_utils.enums import OrderType, OrderStatus, StrategyType
from spectuel_engine_utils.commands import SingleOrderMeta
from spectuel_engine_utils.models import CustomBaseModel


class OrderBase(SingleOrderMeta):
    order_id: UUID = Field(exclude=True)
    user_id: UUID = Field(exclude=True)


class OrderCreateBase(CustomBaseModel):
    strategy_type: StrategyType
    symbol: str


class SingleOrderCreate(OrderCreateBase, OrderBase):
    pass


class OCOOrderCreate(OrderCreateBase):
    legs: list[OrderBase] = Field(min_length=2, max_length=2)

    @field_validator("legs", mode="after")
    def validate_legs(cls, legs: list[OrderBase]):
        if any(o.order_type == OrderType.MARKET for o in legs):
            raise ValueError("OCO legs cannot be market orders.")
        return legs


# class OrderCreate(OrderBase):
#     limit_price: float | None = Field(None, ge=0)
#     stop_price: float | None = Field(None, ge=0)

#     @model_validator(mode="before")
#     def validate_order_details(cls, values):
#         ot = values.get("order_type")

#         if ot == OrderType.MARKET.value:
#             return values

#         if ot == OrderType.LIMIT.value and values.get("limit_price") is None:
#             raise ValueError("Must provide limit price for limit orders.")

#         if ot == OrderType.STOP.value and values.get("stop_price") is None:
#             raise ValueError("Must provide stop price for stop orders.")

#         return values


class OTOOrderCreate(OrderCreateBase):
    parent: OrderBase
    child: OrderBase

    @field_validator("child", mode="after")
    def validate_child(cls, child: OrderBase):
        if child.order_type == OrderType.MARKET:
            raise ValueError("OTO child cannot be a market order")
        return child

    def model_post_init(self, context):
        if self.parent.quantity != self.child.quantity:
            raise ValueError("Parent and child must have the same quantity")
        return self


class OTOCOOrderCreate(BaseModel):
    parent: OrderBase
    oco_legs: list[OrderBase] = Field(min_length=2, max_length=2)

    def model_post_init(self, context):
        quantity = self.parent.quantity

        if any(leg.quantity != quantity for leg in self.oco_legs):
            raise ValueError("OTOCO parent and leg orders must have the same quantity")
        if any(leg.order_type != OrderType.MARKET for leg in self.oco_legs):
            raise ValueError("OTOCO oco legs must cannot be market orders")

        return self


class OrderModify(BaseModel):
    limit_price: float | None = None
    stop_price: float | None = None


class OrderRead(OrderBase):
    order_id: UUID
    strategy_type: StrategyType
    status: OrderStatus
    executed_quantity: float
    avg_fill_price: float | None = None
    created_at: datetime
