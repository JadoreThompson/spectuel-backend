from spectuel_engine_utils.enums import OrderType, StrategyType
from spectuel_engine_utils.events.enums import OrderEventType

from engine.enums import MatchOutcome
from engine.execution_context import ExecutionContext
from engine.engine.types import MatchResult
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
                ctx.wal_logger.log_order_event(
                    order.user_id,
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    details={"reason": "Insufficient funds"},
                )
                return

            if result.outcome == MatchOutcome.SUCCESS:
                return

        # Add to orderbook/store if not fully matched
        ctx.order_store.add(order)
        ctx.orderbook.append(order, order.price)

        ctx.wal_logger.log_order_event(
            order.user_id,
            type=OrderEventType.ORDER_PLACED,
            order_id=order.id,
            symbol=ctx.symbol,
            executed_quantity=order.executed_quantity,
            quantity=order.quantity,
            price=order.price,
            side=order.side,
        )

        # ctx.wal_logger.log_order_event(
        #     order.user_id,
        #     type=OrderEventType.ORDER_PARTIALLY_FILLED,
        #     order_id=order.id,
        #     symbol=ctx.symbol,
        #     executed_quantity=order.executed_quantity,
        #     quantity=order.quantity,
        #     price=price,
        # )

    def handle_filled(
        self, quantity: int, price: float, order: Order, ctx: ExecutionContext
    ):
        if order.executed_quantity == order.quantity:
            ctx.order_store.remove(order)

    def handle_cancel(self, order: Order, ctx: ExecutionContext) -> None:
        ctx.orderbook.remove(order, order.price)
        ctx.order_store.remove(order)
        ctx.wal_logger.log_order_event(
            order.user_id,
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.id,
            symbol=ctx.symbol,
            details={"reason": "Cancelled"},
        )

    def modify(self, cmd: dict, order: Order, ctx: ExecutionContext) -> None:
        self._modify_order(cmd, order, ctx)
        ctx.wal_logger.log_order_event(
            order.user_id,
            type=OrderEventType.ORDER_MODIFIED,
            order_id=order.id,
            symbol=ctx.symbol,
            limit_price=cmd.get("limit_price"),
            stop_price=cmd.get("stop_price"),
            details={},
        )
