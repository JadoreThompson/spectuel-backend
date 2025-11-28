from enum import Enum
from typing import Literal
from uuid import UUID

from enums import Side
from models import CustomBaseModel


class OrderEventType(str, Enum):
    ORDER_PLACED = "placed"
    ORDER_PARTIALLY_FILLED = "partially_filled"
    ORDER_FILLED = "filled"
    ORDER_MODIFIED = "modified"
    ORDER_CANCELLED = "order_cancelled"


class OrderEvent(CustomBaseModel):
    type: OrderEventType = OrderEventType.ORDER_PLACED
    order_id: UUID


class OrderPlacedEvent(CustomBaseModel):
    type: Literal[OrderEventType.ORDER_PLACED] = OrderEventType.ORDER_PLACED
    instrument_id: UUID
    executed_quantity: int
    total_quantity: int
    price: float
    side: Side


class OrderPartiallyFilledEvent(CustomBaseModel):
    type: Literal[OrderEventType.ORDER_PARTIALLY_FILLED] = (
        OrderEventType.ORDER_PARTIALLY_FILLED
    )
    instrument_id: UUID
    executed_quantity: int
    total_quantity: int
    price: float


class OrderFilledEvent(OrderPartiallyFilledEvent):
    type: Literal[OrderEventType.ORDER_FILLED] = OrderEventType.ORDER_FILLED


class OrderModifiedEvent(CustomBaseModel):
    type: Literal[OrderEventType.ORDER_MODIFIED] = OrderEventType.ORDER_MODIFIED
    limit_price: float | None = None
    stop_price: float | None = None

    def model_post_init(self, context):
        if self.limit_price is None and self.stop_price is None:
            raise ValueError("Either limit price or stop price must be provided.")
        return self


class OrderCancelledEvent(CustomBaseModel):
    type: Literal[OrderEventType.ORDER_CANCELLED] = OrderEventType.ORDER_CANCELLED
