from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from spectuel_engine_utils.enums import OrderType

from engine.execution_context import ExecutionContext
from engine.orders import Order


T = TypeVar("T", bound=Order)


class StrategyBase(ABC, Generic[T]):
    @abstractmethod
    def handle_new(self, cmd: dict, ctx: ExecutionContext) -> None:
        """
        Handles the creation of the orders for the strategy

        Args:
            cmd (dict): Dictionary form of the NewOrderCommand
                for that strategy type
            ctx (ExecutionContext): Current execution context
        """

    @abstractmethod
    def handle_filled(
        self, quantity: int, price: float, order: T, ctx: ExecutionContext
    ):
        """Handles the actions necessary when an order is filled."""

    @abstractmethod
    def handle_cancel(self, order: T, ctx: ExecutionContext) -> None:
        """Handles the cancelling of the order"""

    @abstractmethod
    def modify(self, cmd: dict, order: T, ctx: ExecutionContext) -> None:
        """
        Handles the modification of the order

        Args:
            cmd (dict): Dictonary form of a modify order command
            order (Order): The order object being modified
            ctx (ExecutionContext): The current execution context
        """
