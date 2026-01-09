from engine.enums import MatchOutcome, OrderType, StrategyType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.types import MatchResult
from engine.utils import get_price_key, limit_crossable, stop_crossable
from engine.orders import Order
from .base import StrategyBase
from .mixins import ModifyOrderMixin


class SingleOrderStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext) -> None:
        if cmd["order_type"] == OrderType.MARKET:
            price = ctx.orderbook.price
        else:
            price = cmd[get_price_key(cmd["order_type"])]

        order = Order(
            id_=cmd["order_id"],
            user_id=cmd["user_id"],
            strategy_type=StrategyType.SINGLE,
            order_type=cmd["order_type"],
            side=cmd["side"],
            quantity=cmd["quantity"],
            price=price,
        )

        # Determine if the order is immediately matchable
        if cmd["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(order.price, order.side, ctx.orderbook)
        elif cmd["order_type"] == OrderType.STOP:
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
                    {"key": ctx.symbol},
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    details={"reason": "Insufficient funds"},
                    command_id=ctx.cur_command_id,
                )
                ctx.engine._release_escrow(order)
                return

            if result.outcome == MatchOutcome.SUCCESS:
                return

        # Add to orderbook/store if not fully matched
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol},
            type=OrderEventType.ORDER_PLACED,
            order_id=order.id,
            symbol=ctx.symbol,
            executed_quantity=order.executed_quantity,
            quantity=order.quantity,
            price=order.price,
            side=order.side,
            command_id=ctx.cur_command_id,
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
            {"key": ctx.symbol},
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.id,
            symbol=ctx.symbol,
            details={"reason": "User cancelled order."},
            command_id=ctx.cur_command_id,
        )
        ctx.orderbook.remove(order, order.price)
        ctx.order_store.remove(order)
        ctx.engine._release_escrow(order)

    def modify(self, cmd: dict, order: Order, ctx: ExecutionContext) -> None:
        self._modify_order(cmd, order, ctx)
