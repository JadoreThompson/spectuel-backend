from __future__ import annotations
from engine.orders import (
    Order, 
    # These classes have to be in scope
    # during deserialisation phase
    OCOOrder, 
    OTOCOOrder, 
    OTOOrder
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

    def serialise(self, prev: dict | None = None, nxt: dict | None = None):
        uid = id(self)

        s = {"id": uid, "order": self.order.serialise(), "next": None, "prev": None}

        if prev:
            s["prev"] = prev
        elif self.prev:
            s["prev"] = self.prev.serialise(nxt=s)
        else:
            s["prev"] = None

        if nxt:
            s["next"] = nxt
        elif self.next:
            s["next"] = self.next.serialise(prev=s)
        else:
            s["next"] = None

        return s

    @staticmethod
    def deserialise(
        data: dict | None, seen: dict | None = None
    ) -> PriceLevelNode | None:
        if data is None:
            return None

        if seen is None:
            seen = {}

        uid = data["id"]
        if uid in seen:
            return seen[uid]

        cls: Order = eval(data["order"]["type"])
        order = cls.deserialise(data["order"])
        node = PriceLevelNode(order)
        seen[uid] = node

        node.prev = PriceLevelNode.deserialise(data["prev"], seen)
        node.next = PriceLevelNode.deserialise(data["next"], seen)

        return node
