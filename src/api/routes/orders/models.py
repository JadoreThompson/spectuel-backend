from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# from spectuel_engine_utils.enums import OrderType, OrderStatus, StrategyType, Side
# from spectuel_engine_utils.models import CustomBaseModel
from engine.enums import OrderType, OrderStatus, StrategyType, Side
from models import CustomBaseModel

class OrderBase(CustomBaseModel):
    order_type: OrderType
    side: Side
    quantity: float = Field(g=0)
    limit_price: float | None = Field(None, gt=0.0)
    stop_price: float | None = Field(None, gt=0.0)

    @field_validator("order_type", mode="after")
    def validate_order_typee(cls, v):
        if v == OrderType.MARKET:
            raise ValueError("Market orders are not supported")
        return v

    @field_validator("quantity", mode="after")
    def validate_quantity(cls, v):
        v = round(v, 2)
        if v:
            return v
        raise ValueError("Quantity must be greater than zero")


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
    symbol: str
    strategy_type: StrategyType
    status: OrderStatus
    executed_quantity: float
    avg_fill_price: float | None = None
    created_at: datetime
