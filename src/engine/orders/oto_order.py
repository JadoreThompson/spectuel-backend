from __future__ import annotations
from engine.enums import OrderType, Side, StrategyType
from .order import Order


class OTOOrder(Order):
    def __init__(
        self,
        id_: str,
        user_id: str,
        strategy_type: StrategyType,
        order_type: OrderType,
        side: Side,
        quantity: int,
        price: float,
        *,
        parent: OTOOrder | None = None,
        child: OTOOrder | None = None,
    ) -> None:
        super().__init__(id_, user_id, strategy_type, order_type, side, quantity, price)
        self.parent = parent
        self.child = child
        # The parent order is triggered by default; the child is not.
        self.triggered = parent is None

    def to_dict(self, parent: dict | None = None, child: dict | None = None) -> dict:
        s = super().to_dict()

        if parent:
            s["parent"] = parent
        elif self.parent is None:
            s["parent"] = None
        else:
            s["parent"] = self.parent.to_dict(s)

        if child:
            s["child"] = child
        elif self.child is None:
            s["child"] = None
        else:
            s["child"] = self.child.to_dict(s)

        s["triggered"] = self.triggered

        return s

    @classmethod
    def from_dict(cls, data: dict, is_child: bool = False) -> OTOOrder:
        parent = data.get("parent")
        child = data.get("child")

        if is_child:
            parent_order = None
        elif parent is None:
            parent_order = None
        else:
            parent_order = OTOOrder.from_dict(parent, is_child=True)

        if is_child:
            child_order = None
        elif child is None:
            child_order = None
        else:
            child_order = OTOOrder.from_dict(child, is_child=True)

        order = cls(
            id_=data["id"],
            user_id=data["user_id"],
            strategy_type=StrategyType(data["strategy_type"]),
            order_type=OrderType(data["order_type"]),
            side=Side(data["side"]),
            quantity=data["quantity"],
            price=data["price"],
            parent=parent_order,
            child=child_order,
        )

        order.triggered = data["triggered"]

        return order
