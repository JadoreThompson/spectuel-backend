from __future__ import annotations
from engine.orders import (
    Order,
    # These classes have to be in scope
    # during deserialisation phase
    OCOOrder,
    OTOCOOrder,
    OTOOrder,
)


class PriceLevelNode:
    """
    Doubly linked list to house an order within
    a PriceLevel.
    """

    def __init__(
        self,
        order: Order,
        prev: PriceLevelNode | None = None,
        next: PriceLevelNode | None = None,
    ) -> None:
        self.order = order
        self.prev = prev
        self.next = next

    def to_dict(self):
        uid = id(self)

        s = {"id": uid, "order": self.order.to_dict(), "next": None}

        if self.next is not None:
            s["next"] = self.next.to_dict()

        return s

    @staticmethod
    def from_dict(data: dict, prev: Order | None = None) -> PriceLevelNode | None:
        if not data:
            return

        cls: Order = eval(data["order"]["type"])
        order = cls.from_dict(data["order"])
        node = PriceLevelNode(order)

        node.prev = prev
        node.next = PriceLevelNode.from_dict(data["next"], node)

        return node
