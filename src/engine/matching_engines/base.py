from abc import ABC, abstractmethod

from engine.execution_context import ExecutionContext
from engine.types import MatchResult
from orders import Order


class EngineBase(ABC):
    @abstractmethod
    def handle_command(self, cmd: dict) -> None: ...

    @abstractmethod
    def match(self, taker_order: Order, ctx: ExecutionContext) -> MatchResult: ...
