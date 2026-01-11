from __future__ import annotations
from typing import TYPE_CHECKING

from engine.loggers import EngineLogger
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
        orderbook: OrderBook,
        order_store: OrderStore,
        symbol: str,
        engine: "EngineBase" | None = None,
        cur_command_id: str | None = None,
        engine_logger: EngineLogger | None = None,
    ) -> None:
        self.engine = engine
        self.orderbook = orderbook
        self.order_store = order_store
        self.symbol = symbol
        self.cur_command_id = cur_command_id  # Current command being executed
        self.engine_logger: EngineLogger = engine_logger or EngineLogger(symbol)

    def to_dict(self) -> dict:
        return {
            "orderbook": self.orderbook.to_dict(),
            "order_store": self.order_store.to_dict(),
            "symbol": self.symbol,
            "cur_command_id": self.cur_command_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        engine: "EngineBase" | None = None,
    ) -> ExecutionContext:
        orderbook = OrderBook.from_dict(data["orderbook"])
        order_store = OrderStore.from_dict(data["order_store"])

        return cls(
            engine=engine,
            orderbook=orderbook,
            order_store=order_store,
            symbol=data["symbol"],
            cur_command_id=data.get("cur_command_id"),
        )
