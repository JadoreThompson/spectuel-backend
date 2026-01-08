from engine.enums import StrategyType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.utils import get_price_key
from engine.orders import OCOOrder
from .base import StrategyBase
from .mixins import ModifyOrderMixin


class OCOStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext) -> None:
        leg_a, leg_b = cmd["legs"]

        order_a = OCOOrder(
            id_=leg_a["order_id"],
            user_id=leg_a["user_id"],
            strategy_type=StrategyType.OCO,
            side=leg_a["side"],
            order_type=leg_a["order_type"],
            quantity=leg_a["quantity"],
            price=leg_a[get_price_key(leg_a["order_type"])],
        )

        order_b = OCOOrder(
            id_=leg_b["order_id"],
            user_id=leg_b["user_id"],
            strategy_type=StrategyType.OCO,
            side=leg_b["side"],
            order_type=leg_b["order_type"],
            quantity=leg_b["quantity"],
            price=leg_b[get_price_key(leg_b["order_type"])],
        )

        order_a.counterparty = order_b
        order_b.counterparty = order_a

        ctx.logger.log_order_event(
            order_a.user_id,
            type=OrderEventType.ORDER_PLACED,
            order_id=order_a.id,
            symbol=ctx.symbol,
            executed_quantity=order_a.executed_quantity,
            quantity=order_a.quantity,
            price=order_a.price,
            side=order_a.side,
            command_id=ctx.command_id,
        )
        ctx.logger.log_order_event(
            order_b.user_id,
            type=OrderEventType.ORDER_PLACED,
            order_id=order_b.id,
            symbol=ctx.symbol,
            executed_quantity=order_b.executed_quantity,
            quantity=order_b.quantity,
            price=order_b.price,
            side=order_b.side,
            command_id=ctx.command_id,
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
        ctx.logger.log_order_event(
            order.user_id,
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.counterparty.id,
            symbol=ctx.symbol,
            command_id=ctx.command_id,
            details={"reason": f"OCO peer {order.id} was filled."},
        )
        ctx.orderbook.remove(counterparty, counterparty.price)
        ctx.order_store.remove(counterparty)
        ctx.engine._release_escrow(order)


    def handle_cancel(self, order: OCOOrder, ctx: ExecutionContext) -> None:
        # WAL log both legs
        counterparty = order.counterparty
        ctx.logger.log_order_event(
            order.user_id,
            type=OrderEventType.ORDER_CANCELLED,
            order_id=order.id,
            symbol=ctx.symbol,
            command_id=ctx.command_id,
            details={"reason": "Client requested cancel."},
        )
        ctx.logger.log_order_event(
            order.user_id,
            type=OrderEventType.ORDER_CANCELLED,
            order_id=counterparty.id,
            symbol=ctx.symbol,
            command_id=ctx.command_id,
            details={"reason": "Client requested cancel."},
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
