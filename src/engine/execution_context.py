import threading
from typing import TYPE_CHECKING

from engine.loggers.wal_logger import WALogger
from .orderbook import OrderBook
from .stores import OrderStore

if TYPE_CHECKING:
    from .matching_engines import EngineBase


class ExecutionContext:
    """
    An empty container object passed to strategy handlers
    """

    def __init__(
        self,
        *,
        engine: "EngineBase",
        orderbook: OrderBook,
        order_store: OrderStore,
        symbol: str,
        command_id: str | None = None,
    ) -> None:
        self.engine = engine
        self.orderbook = orderbook
        self.order_store = order_store
        self.symbol = symbol
        self.command_id = command_id  # Current command being executed
        self.lock = threading.Lock()
        self.wal_logger = WALogger(symbol)

    def serialise(self) -> dict:
        return {
            "orderbook": self.orderbook.serialise(),
            "order_store": self.order_store.serialise(),
            "symbol": self.symbol,
            "command_id": self.command_id if self.command_id else None,
        }

    @classmethod
    def deserialise(
        cls,
        data: dict,
        *,
        engine: "EngineBase",
    ) -> "ExecutionContext":
        orderbook = OrderBook.deserialise(data["orderbook"])
        order_store = OrderStore.deserialise(data["order_store"])

        return cls(
            engine=engine,
            orderbook=orderbook,
            order_store=order_store,
            symbol=data["symbol"],
            command_id=data["command_id"],
        )
