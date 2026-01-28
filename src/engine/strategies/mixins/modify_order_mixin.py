from engine.enums import OrderType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.utils import get_price_key, limit_crossable, stop_crossable
from engine.orders import Order


class ModifyOrderMixin:
    def _get_modified_price(self, cmd: dict, order: Order) -> float:
        new_price = order.price

        if cmd["limit_price"] is not None and order.order_type == OrderType.LIMIT:
            new_price = cmd["limit_price"]

        if cmd["stop_price"] is not None and order.order_type == OrderType.STOP:
            new_price = cmd["stop_price"]

        return new_price

    def _validate_modify(self, cmd: dict, order: Order, ctx: ExecutionContext) -> bool:
        if cmd["limit_price"] is not None and order.order_type == OrderType.LIMIT:
            if limit_crossable(cmd["limit_price"], order.side, ctx.orderbook):
                ctx.engine_logger.log_order_event(
                    order.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_MODIFY_REJECTED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    command_id=ctx.cur_command_id,
                    reason="Modification would cross the spread.",
                )
                return False

        if cmd["stop_price"] is not None and order.order_type == OrderType.STOP:
            if stop_crossable(cmd["stop_price"], order.side, ctx.orderbook):
                ctx.engine_logger.log_order_event(
                    order.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_MODIFY_REJECTED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    command_id=ctx.cur_command_id,
                    reason="Modification would cross the spread.",
                )
                return False

        return True

    # TODO: Check if user has sufficient balance for modified order
    def _modify_order(self, cmd: dict, order: Order, ctx: ExecutionContext) -> None:
        if not self._validate_modify(cmd, order, ctx):
            return

        new_price = self._get_modified_price(cmd, order)
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_MODIFIED,
            order_id=order.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            **{get_price_key(order.order_type): new_price}
        )
        ctx.orderbook.remove(order, order.price)
        order.price = new_price
        ctx.orderbook.append(order, order.price)
