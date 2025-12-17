from typing import Literal
from uuid import UUID

from engine.enums import Side
from engine.events import EngineEventBase
from .enums import OrderEventType


class OrderEventBase(EngineEventBase):
    version: int = 1
    order_id: UUID


class OrderPlacedEvent(OrderEventBase):
    type: Literal[OrderEventType.ORDER_PLACED] = OrderEventType.ORDER_PLACED
    symbol: str
    executed_quantity: float
    quantity: float
    price: float
    side: Side


class OrderFilledEventBase(OrderEventBase):
    symbol: str
    executed_quantity: float
    quantity: float
    price: float


class OrderPartiallyFilledEvent(OrderFilledEventBase):
    type: Literal[OrderEventType.ORDER_PARTIALLY_FILLED] = (
        OrderEventType.ORDER_PARTIALLY_FILLED
    )


class OrderFilledEvent(OrderFilledEventBase):
    type: Literal[OrderEventType.ORDER_FILLED] = OrderEventType.ORDER_FILLED


class OrderModifiedEvent(OrderEventBase):
    type: Literal[OrderEventType.ORDER_MODIFIED] = OrderEventType.ORDER_MODIFIED
    limit_price: float | None = None
    stop_price: float | None = None

    def model_post_init(self, context):
        if self.limit_price is None and self.stop_price is None:
            raise ValueError("Either limit price or stop price must be provided.")
        return self


class OrderModifyRejectedEvent(OrderEventBase):
    type: Literal[OrderEventType.ORDER_MODIFY_REJECTED] = (
        OrderEventType.ORDER_MODIFY_REJECTED
    )
    symbol: str
    reason: str


class OrderCancelledEvent(OrderEventBase):
    type: Literal[OrderEventType.ORDER_CANCELLED] = OrderEventType.ORDER_CANCELLED
    symbol: str
