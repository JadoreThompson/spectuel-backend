from engine.orders import Order
from .base import StoreBase


class OrderStore(StoreBase[Order]):
    def __init__(self):
        self._orders: dict[str, Order] = {}

    def add(self, value: Order) -> None:
        self._orders.setdefault(value.id, value)

    def remove(self, value: Order) -> None:
        self._orders.pop(value.id, None)

    def get(self, value: str) -> Order | None:
        return self._orders.get(value)

    def serialise(self) -> dict:
        return {order_id: order.serialise() for order_id, order in self._orders.items()}

    @classmethod
    def deserialise(cls, data: dict) -> "OrderStore":
        store = cls()
        for _, order_data in data.items():
            cls: Order = eval(order_data["type"])
            order = cls.deserialise(order_data)
            store.add(order)
        return store
