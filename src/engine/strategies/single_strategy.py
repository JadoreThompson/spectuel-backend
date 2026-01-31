from engine.enums import MatchOutcome, OrderStatus, OrderType, StrategyType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.types import MatchResult
from engine.utils import get_price_key, limit_crossable, stop_crossable
from engine.orders import Order
from .base import StrategyBase
from .mixins import ModifyOrderMixin


class SingleOrderStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext) -> None:
        order_dict = cmd["order"].copy()

        # Set the effective price for market orders
        if order_dict["order_type"] == OrderType.MARKET.value:
            order_dict["limit_price"] = ctx.orderbook.price

        order = Order(order_dict=order_dict)

        # Determine if the order is immediately matchable
        if order_dict["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(order.price, order.side, ctx.orderbook)
        elif order_dict["order_type"] == OrderType.STOP:
            matchable = stop_crossable(order.price, order.side, ctx.orderbook)
        else:
            matchable = True

        # Attempt to match immediately if possible
        if matchable:
            result: MatchResult = ctx.engine.match(order, ctx)
            order.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.INSUFFICIENT_BALANCE:
                ctx.engine_logger.log_order_event(
                    order.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    details={"reason": "Insufficient funds"},
                    command_id=ctx.cur_command_id,
                    order=order.get_order_dict(),
                )
                ctx.engine._release_escrow(order)
                return

            if result.outcome == MatchOutcome.SUCCESS:
                return

        # Add to orderbook/store if not fully matched
        order.status = OrderStatus.PLACED
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_PLACED,
            order_id=order.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            order=order.get_order_dict(),
        )

        ctx.order_store.add(order)
        ctx.orderbook.append(order, order.price)

    def handle_filled(
        self, quantity: int, price: float, order: Order, ctx: ExecutionContext
    ):
        """
        If the order is fully filled the engine would've already removed it from
        both the orderbook and the order store.
        """

    def handle_cancel(self, order: Order, ctx: ExecutionContext) -> None:
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.id,
            symbol=ctx.symbol,
            details={"reason": "User cancelled order."},
            command_id=ctx.cur_command_id,
            order=order.get_order_dict(),
        )
        ctx.orderbook.remove(order, order.price)
        ctx.order_store.remove(order)
        ctx.engine._release_escrow(order)

    def modify(self, cmd: dict, order: Order, ctx: ExecutionContext) -> None:
        self._modify_order(cmd, order, ctx)
