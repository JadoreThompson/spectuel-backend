from __future__ import annotations
from spectuel_engine_utils.enums import OrderType, Side, StrategyType
from .order import Order


class OCOOrder(Order):
    def __init__(
        self,
        id_,
        user_id,
        strategy_type,
        order_type,
        side,
        quantity,
        price,
        *,
        counterparty: OCOOrder | None = None,
    ):
        super().__init__(id_, user_id, strategy_type, order_type, side, quantity, price)
        self.counterparty = counterparty

    def serialise(self, counterparty: dict | None =None) -> dict:
        s = super().serialise()

        if counterparty:
            s["counterparty"] = counterparty
        elif self.counterparty is None:
            s["counterparty"] = None
        else:
            s["counterparty"] = self.counterparty.serialise(s)

        return s
    
    @classmethod
    def deserialise(cls, data: dict, is_counterparty: bool = False) -> OCOOrder:
        counterparty = data.get("counterparty")

        if is_counterparty:
            counterparty_order = None
        elif counterparty is None:
            counterparty_order = None
        else:
            counterparty_order = OCOOrder.deserialise(counterparty, is_counterparty=True)

        order = cls(
            id_=data["id"],
            user_id=data["user_id"],
            strategy_type=StrategyType(data["strategy_type"]),
            order_type=OrderType(data["order_type"]),
            side=Side(data["side"]),
            quantity=data["quantity"],
            price=data["price"],
            counterparty=counterparty_order,
        )
        
        if not is_counterparty and counterparty_order:
            counterparty_order.counterparty = order

        return order
