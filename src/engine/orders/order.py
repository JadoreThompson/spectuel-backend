from __future__ import annotations
from engine.enums import OrderType, Side, StrategyType


class Order:
    def __init__(
        self,
        id_: str,
        user_id: str,
        strategy_type: StrategyType,
        order_type: OrderType,
        side: Side,
        quantity: int,
        price: float,
    ):
        self.id = id_
        self.user_id = user_id
        self.strategy_type = strategy_type
        self.order_type = order_type
        self.side = side
        self.quantity = quantity
        self.executed_quantity = 0
        self.price = price

    def to_dict(self) -> dict:
        s = vars(self)
        s["type"] = self.__class__.__name__
        return s

    @classmethod
    def from_dict(cls, data: dict) -> Order:
        return cls(
            id_=data["id"],
            user_id=data["user_id"],
            strategy_type=StrategyType(data["strategy_type"]),
            order_type=OrderType(data["order_type"]),
            side=Side(data["side"]),
            quantity=data["quantity"],
            price=data["price"],
        )
