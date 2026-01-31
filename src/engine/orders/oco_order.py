from __future__ import annotations
from .order import Order


class OCOOrder(Order):
    def __init__(self, order_dict: dict, counterparty: OCOOrder | None = None):
        super().__init__(order_dict)
        self.counterparty = counterparty

    def to_dict(self, counterparty: dict | None = None) -> dict:
        s = super().to_dict()

        if counterparty:
            s["counterparty"] = counterparty
        elif self.counterparty is None:
            s["counterparty"] = None
        else:
            s["counterparty"] = self.counterparty.to_dict(s)

        return s

    @classmethod
    def from_dict(cls, data: dict, is_counterparty: bool = False) -> OCOOrder:
        counterparty = data.get("counterparty")

        if is_counterparty:
            counterparty_order = None
        elif counterparty is None:
            counterparty_order = None
        else:
            counterparty_order = OCOOrder.from_dict(counterparty, is_counterparty=True)

        order_dict = data.get("order_dict", data)
        order = cls(order_dict=order_dict, counterparty=counterparty_order)

        if not is_counterparty and counterparty_order:
            counterparty_order.counterparty = order

        return order
