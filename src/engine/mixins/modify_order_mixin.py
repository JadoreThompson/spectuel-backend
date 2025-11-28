from enums import EventType, OrderType
from ..event_logger import EventLogger
from ..execution_context import ExecutionContext
from ..models import MODIFY_SENTINEL, ModifyOrderCommand
from ..orders import Order
from ..utils import limit_crossable, stop_crossable


class ModifyOrderMixin:
    def _get_modified_price(self, command: ModifyOrderCommand, order: Order) -> float:
        new_price = order.price

        if (
            command.limit_price != MODIFY_SENTINEL
            and order.order_type == OrderType.LIMIT
        ):
            new_price = command.limit_price

        if command.stop_price != MODIFY_SENTINEL and order.order_type == OrderType.STOP:
            new_price = command.stop_price

        return new_price

    def _validate_modify(
        self, command: ModifyOrderCommand, order: Order, ctx: ExecutionContext
    ) -> bool:
        log_modify_reject = lambda: EventLogger.log_event(
            EventType.ORDER_MODIFY_REJECTED,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=ctx.instrument_id,
            details={"reason": "Modification would cross the spread."},
        )

        if (
            command.limit_price != MODIFY_SENTINEL
            and order.order_type == OrderType.LIMIT
        ):
            if limit_crossable(command.limit_price, order.side, ctx.orderbook):
                log_modify_reject()
                return False

        if command.stop_price != MODIFY_SENTINEL and order.order_type == OrderType.STOP:
            if stop_crossable(command.stop_price, order.side, ctx.orderbook):
                log_modify_reject()
                return False

        return True

    def _modify_order(
        self, command: ModifyOrderCommand, order: Order, ctx: ExecutionContext
    ) -> None:
        if not self._validate_modify(command, order, ctx):
            return

        new_price = self._get_modified_price(command, order)
        ctx.orderbook.remove(order, order.price)
        order.price = new_price
        ctx.orderbook.append(order, order.price)
        EventLogger.log_event(
            EventType.ORDER_MODIFIED,
            user_id=order.user_id,
            related_id=order.id,
            instrument_id=ctx.instrument_id,
            details={"price": new_price},
        )
