import threading
from __future__ import annotations
from typing import TYPE_CHECKING, Generic, TypeVar

from engine.loggers import EngineLogger
from engine.orderbook import OrderBook
from engine.stores import OrderStore

if TYPE_CHECKING:
    from engine.matching_engines import EngineBase


ELT = TypeVar("LT", boudn=EngineLogger)


class ExecutionContext(Generic[ELT]):
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
        cur_command_id: str | None = None,
        prev_commited_command_id: str | None = None,
        prev_command_id: str | None = None,
        engine_logger: ELT | None = None,
    ) -> None:
        self.engine = engine
        self.orderbook = orderbook
        self.order_store = order_store
        self.symbol = symbol
        self.cur_command_id = cur_command_id  # Current command being executed
        self.prev_commited_command_id = (
            prev_commited_command_id  # Last fully processed command id
        )
        self.prev_command_id = prev_command_id
        self.engine_logger: ELT = engine_logger or EngineLogger(symbol)

    def to_dict(self) -> dict:
        return {
            "orderbook": self.orderbook.to_dict(),
            "order_store": self.order_store.to_dict(),
            "symbol": self.symbol,
            "cur_command_id": self.cur_command_id,
            "prev_commited_command_id": self.prev_commited_command_id,
            "prev_command_id": self.prev_command_id,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        engine: "EngineBase",
    ) -> ExecutionContext:
        orderbook = OrderBook.from_dict(data["orderbook"])
        order_store = OrderStore.from_dict(data["order_store"])

        return cls(
            engine=engine,
            orderbook=orderbook,
            order_store=order_store,
            symbol=data["symbol"],
            command_id=data["command_id"],
            prev_commited_command_id=data["prev_commited_command_id"],
            prev_command_id=data["prev_command_id"],
        )
