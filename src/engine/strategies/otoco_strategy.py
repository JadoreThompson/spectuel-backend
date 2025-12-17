from spectuel_engine_utils.enums import OrderType, StrategyType
from spectuel_engine_utils.events.enums import OrderEventType

from engine.enums import MatchOutcome
from engine.execution_context import ExecutionContext
from engine.utils import get_price_key, limit_crossable, stop_crossable
from engine.orders import OTOCOOrder
from .base import StrategyBase
from .mixins import ModifyOrderMixin


class OTOCOStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext):
        parent_data = cmd["parent"]
        child_leg_a_data, child_leg_b_data = cmd["oco_legs"]

        if parent_data["order_type"] == OrderType.MARKET:
            parent_price = ctx.orderbook.price
        else:
            parent_price = parent_data[get_price_key(parent_data["order_type"])]

        parent_order = OTOCOOrder(
            id_=parent_data["order_id"],
            user_id=parent_data["user_id"],
            strategy_type=StrategyType.OTOCO,
            order_type=parent_data["order_type"],
            side=parent_data["side"],
            quantity=parent_data["quantity"],
            price=parent_price,
        )

        child_a = OTOCOOrder(
            id_=child_leg_a_data["order_id"],
            user_id=child_leg_a_data["user_id"],
            strategy_type=StrategyType.OTOCO,
            order_type=child_leg_a_data["order_type"],
            side=child_leg_a_data["side"],
            quantity=child_leg_a_data["quantity"],
            price=child_leg_a_data[get_price_key(child_leg_a_data["order_type"])],
            parent=parent_order,
        )

        child_b = OTOCOOrder(
            id_=child_leg_b_data["order_id"],
            user_id=child_leg_b_data["user_id"],
            strategy_type=StrategyType.OTOCO,
            order_type=child_leg_b_data["order_type"],
            side=child_leg_b_data["side"],
            quantity=child_leg_b_data["quantity"],
            price=child_leg_b_data[get_price_key(child_leg_b_data["order_type"])],
            parent=parent_order,
        )

        parent_order.child_a = child_a
        parent_order.child_b = child_b
        child_a.counterparty = child_b
        child_b.counterparty = child_a

        ctx.order_store.add(parent_order)
        ctx.order_store.add(child_a)
        ctx.order_store.add(child_b)

        # Check if parent is matchable
        matchable = True
        if parent_data["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(
                parent_data["limit_price"], parent_order.side, ctx.orderbook
            )
        if parent_data["order_type"] == OrderType.STOP:
            matchable = stop_crossable(
                parent_data["stop_price"], parent_order.side, ctx.orderbook
            )

        if matchable:
            result = ctx.engine.match(parent_order, ctx)
            parent_order.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.INSUFFICIENT_BALANCE:
                return

            if result.outcome == MatchOutcome.SUCCESS:
                ctx.order_store.remove(parent_order)
                ctx.orderbook.append(child_a, child_a.price)
                ctx.orderbook.append(child_b, child_b.price)

                ctx.wal_logger.log_order_event(
                    child_a.user_id,
                    type=OrderEventType.ORDER_PLACED,
                    order_id=child_a.id,
                    symbol=ctx.symbol,
                    executed_quantity=child_a.executed_quantity,
                    quantity=child_a.quantity,
                    price=child_a.price,
                    side=child_a.side,
                )
                ctx.wal_logger.log_order_event(
                    child_b.user_id,
                    type=OrderEventType.ORDER_PLACED,
                    order_id=child_b.id,
                    symbol=ctx.symbol,
                    executed_quantity=child_b.executed_quantity,
                    quantity=child_b.quantity,
                    price=child_b.price,
                    side=child_b.side,
                )
                return

        ctx.orderbook.append(parent_order, parent_order.price)
        ctx.wal_logger.log_order_event(
            parent_order.user_id,
            type=OrderEventType.ORDER_PLACED,
            order_id=parent_order.id,
            symbol=ctx.symbol,
            executed_quantity=parent_order.executed_quantity,
            quantity=parent_order.quantity,
            price=parent_order.price,
            side=parent_order.side,
        )

    def handle_filled(
        self, quantity: int, price: float, order: OTOCOOrder, ctx: ExecutionContext
    ):
        # Parent filled: trigger OCO children
        if order.child_a and order.executed_quantity == order.quantity:
            order.triggered = False
            for child in (order.child_a, order.child_b):
                child.triggered = True
                ctx.orderbook.append(child, child.price)
                ctx.wal_logger.log_order_event(
                    child.user_id,
                    type=OrderEventType.ORDER_PLACED,
                    order_id=child.id,
                    symbol=ctx.symbol,
                    executed_quantity=child.executed_quantity,
                    quantity=child.quantity,
                    price=child.price,
                    side=child.side,
                )
            ctx.order_store.remove(order)
            return

        # Child filled: cancel its counterparty
        if order.counterparty and order.executed_quantity == order.quantity:
            counterparty = order.counterparty
            ctx.orderbook.remove(counterparty, counterparty.price)
            ctx.order_store.remove(order)
            ctx.order_store.remove(counterparty)
            ctx.wal_logger.log_order_event(
                counterparty.user_id,
                type=OrderEventType.ORDER_CANCELLED,
                order_id=counterparty.id,
                symbol=ctx.symbol,
                details={"reason": f"OCO peer {order.id} was filled."},
            )

    def handle_cancel(self, order: OTOCOOrder, ctx: ExecutionContext) -> None:
        if order.child_a:  # parent
            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order)
            ctx.order_store.remove(order.child_a)
            ctx.order_store.remove(order.child_b)

            ctx.wal_logger.log_order_event(
                order.user_id,
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.id,
                symbol=ctx.symbol,
                details={},
            )
            for child in (order.child_a, order.child_b):
                ctx.wal_logger.log_order_event(
                    child.user_id,
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=child.id,
                    symbol=ctx.symbol,
                    details={"reason": "Parent order cancelled."},
                )
            return

        # child
        counterparty = order.counterparty
        if order.triggered:
            ctx.orderbook.remove(order, order.price)
            ctx.orderbook.remove(counterparty, counterparty.price)
        else:
            ctx.orderbook.remove(order.parent, order.parent.price)

        ctx.order_store.remove(order)
        ctx.order_store.remove(counterparty)
        if order.parent.triggered:
            ctx.wal_logger.log_order_event(
                order.user_id,
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.id,
                symbol=ctx.symbol,
                details={},
            )
        ctx.wal_logger.log_order_event(
            counterparty.user_id,
            type=OrderEventType.ORDER_CANCELLED,
            order_id=counterparty.id,
            symbol=ctx.symbol,
            details={},
        )

    def modify(self, cmd: dict, order: OTOCOOrder, ctx: ExecutionContext):
        if order.triggered:
            self._modify_order(cmd, order, ctx)
        elif self._validate_modify(cmd, order, ctx):
            order.price = self._get_modified_price(cmd, order)
            ctx.wal_logger.log_order_event(
                order.user_id,
                type=OrderEventType.ORDER_MODIFIED,
                order_id=order.id,
                symbol=ctx.symbol,
                **{get_price_key(order.order_type): order.price},
            )
