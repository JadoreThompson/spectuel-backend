from engine.enums import StrategyType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.utils import get_price_key
from engine.orders import OCOOrder
from .base import StrategyBase
from .mixins import ModifyOrderMixin


class OCOStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext) -> None:
        leg_a_dict, leg_b_dict = cmd["legs"]

        order_a = OCOOrder(order_dict=leg_a_dict.copy())
        order_b = OCOOrder(order_dict=leg_b_dict.copy())

        order_a.counterparty = order_b
        order_b.counterparty = order_a

        ctx.engine_logger.log_order_event(
            order_a.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_PLACED,
            order_id=order_a.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            order=order_a.get_order_dict(),
        )
        ctx.engine_logger.log_order_event(
            order_b.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_PLACED,
            order_id=order_b.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            order=order_b.get_order_dict(),
        )

        # Add to orderbook/store
        ctx.orderbook.append(order_a, order_a.price)
        ctx.orderbook.append(order_b, order_b.price)
        ctx.order_store.add(order_a)
        ctx.order_store.add(order_b)

    def handle_filled(
        self, quantity: int, price: float, order: OCOOrder, ctx: ExecutionContext
    ) -> None:
        counterparty = order.counterparty
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.counterparty.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            details={"reason": f"OCO peer {order.id} was filled."},
            order=counterparty.get_order_dict(),
        )
        ctx.orderbook.remove(counterparty, counterparty.price)
        ctx.order_store.remove(counterparty)
        ctx.engine._release_escrow(order)

    def handle_cancel(self, order: OCOOrder, ctx: ExecutionContext) -> None:
        # WAL log both legs
        counterparty = order.counterparty
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            details={"reason": "Client requested cancel."},
            order=order.get_order_dict(),
        )
        ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_CANCELLED,
            order_id=counterparty.id,
            symbol=ctx.symbol,
            command_id=ctx.cur_command_id,
            details={"reason": "Client requested cancel."},
            order=counterparty.get_order_dict(),
        )

        ctx.orderbook.remove(order, order.price)
        ctx.orderbook.remove(counterparty, counterparty.price)
        ctx.order_store.remove(order)
        ctx.order_store.remove(counterparty)

        ctx.engine._release_escrow(order)

    def _cancel(self, order: OCOOrder, ctx: ExecutionContext) -> None:
        ctx.orderbook.remove(order, order.price)
        ctx.orderbook.remove(order.counterparty, order.counterparty.price)
        ctx.order_store.remove(order)
        ctx.order_store.remove(order.counterparty)

        ctx.engine._release_escrow(order)
        ctx.engine._release_escrow(order.counterparty)

    def modify(self, cmd: dict, order: OCOOrder, ctx: ExecutionContext) -> None:
        self._modify_order(cmd, order, ctx)
