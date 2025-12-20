import threading
from typing import TYPE_CHECKING

from engine.loggers.wal_logger import WALogger
from engine.orderbook import OrderBook
from engine.stores import OrderStore

if TYPE_CHECKING:
    from engine.matching_engines import EngineBase


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

    def to_dict(self) -> dict:
        return {
            "orderbook": self.orderbook.to_dict(),
            "order_store": self.order_store.to_dict(),
            "symbol": self.symbol,
            "command_id": self.command_id if self.command_id else None,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        engine: "EngineBase",
    ) -> "ExecutionContext":
        orderbook = OrderBook.from_dict(data["orderbook"])
        order_store = OrderStore.from_dict(data["order_store"])

        return cls(
            engine=engine,
            orderbook=orderbook,
            order_store=order_store,
            symbol=data["symbol"],
            command_id=data["command_id"],
        )
