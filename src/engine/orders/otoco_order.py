from __future__ import annotations
from spectuel_engine_utils.enums import OrderType, Side, StrategyType
from .order import Order


class OTOCOOrder(Order):
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
        parent: OTOCOOrder | None = None,
        child_a: OTOCOOrder | None = None,
        child_b: OTOCOOrder | None = None,
        counterparty: OTOCOOrder | None = None,  # For OCO
    ) -> None:
        super().__init__(id_, user_id, strategy_type, order_type, side, quantity, price)
        self.parent = parent
        self.child_a = child_a
        self.child_b = child_b
        self.counterparty = counterparty
        # The parent order is triggered by default; children are not.
        self.triggered = parent is None

    def serialise(
        self, parent: dict | None =None, child_a: dict | None =None, child_b: dict | None =None, counterparty: dict | None =None
    ) -> dict:
        s = super().serialise()

        if parent:
            s["parent"] = parent
        elif self.parent is None:
            s["parent"] = None
        else:
            s["parent"] = self.parent.serialise(s)

        if child_a:
            s["child_a"] = child_a
        elif self.child_a is None:
            s["child_a"] = None
        else:
            s["child_a"] = self.child_a.serialise(s)

        if child_b:
            s["child_b"] = child_b
        elif self.child_b is None:
            s["child_b"] = None
        else:
            s["child_b"] = self.child_b.serialise(s)

        if counterparty:
            s["counterparty"] = counterparty
        elif self.counterparty is None:
            s["counterparty"] = None
        else:
            s["counterparty"] = self.counterparty.serialise(s)

        s["triggered"] = self.triggered

        return s

    @classmethod
    def deserialise(
        cls, data: dict, is_child: bool = False, is_counterparty: bool = False
    ) -> OTOCOOrder:
        parent = data.get("parent")
        child_a = data.get("child_a")
        child_b = data.get("child_b")
        counterparty = data.get("counterparty")

        if is_child:
            parent_order = None
        elif parent is None:
            parent_order = None
        else:
            parent_order = OTOCOOrder.deserialise(parent, is_child=True)

        if is_child:
            child_a_order = None
        elif child_a is None:
            child_a_order = None
        else:
            child_a_order = OTOCOOrder.deserialise(child_a, is_child=True)

        if is_child:
            child_b_order = None
        elif child_b is None:
            child_b_order = None
        else:
            child_b_order = OTOCOOrder.deserialise(child_b, is_child=True)

        if is_counterparty:
            counterparty_order = None
        elif counterparty is None:
            counterparty_order = None
        else:
            counterparty_order = OTOCOOrder.deserialise(
                counterparty, is_counterparty=True
            )

        order = cls(
            id_=data["id"],
            user_id=data["user_id"],
            strategy_type=StrategyType(data["strategy_type"]),
            order_type=OrderType(data["order_type"]),
            side=Side(data["side"]),
            quantity=data["quantity"],
            price=data["price"],
            parent=parent_order,
            child_a=child_a_order,
            child_b=child_b_order,
            counterparty=counterparty_order,
        )

        if not is_child and parent_order:
            parent_order.child_a = order  # Assuming single linkage for simplicity
        if not is_counterparty and counterparty_order:
            counterparty_order.counterparty = order

        return order
