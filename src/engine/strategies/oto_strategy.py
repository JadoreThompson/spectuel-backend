from engine.enums import MatchOutcome, StrategyType, OrderType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.utils import get_price_key, limit_crossable, stop_crossable
from engine.orders import OTOOrder
from .base import StrategyBase
from .mixins import ModifyOrderMixin


class OTOStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext) -> None:
        parent_data = cmd["parent"]
        child_data = cmd["child"]

        if parent_data["order_type"] == OrderType.MARKET:
            parent_price = ctx.orderbook.price
        else:
            parent_price = parent_data[get_price_key(parent_data["order_type"])]

        parent = OTOOrder(
            id_=parent_data["order_id"],
            user_id=parent_data["user_id"],
            strategy_type=StrategyType.OTO,
            order_type=parent_data["order_type"],
            side=parent_data["side"],
            quantity=parent_data["quantity"],
            price=parent_price,
        )

        child = OTOOrder(
            id_=child_data["order_id"],
            user_id=child_data["user_id"],
            strategy_type=StrategyType.OTO,
            order_type=child_data["order_type"],
            side=child_data["side"],
            quantity=child_data["quantity"],
            price=child_data[get_price_key(child_data["order_type"])],
            parent=parent,
        )

        parent.child = child
        child.parent = parent

        # Check if parent is immediately matchable
        if parent_data["order_type"] == OrderType.LIMIT:
            matchable = limit_crossable(
                parent_data["limit_price"], parent.side, ctx.orderbook
            )
        elif parent_data["order_type"] == OrderType.STOP:
            matchable = stop_crossable(
                parent_data["stop_price"], parent.side, ctx.orderbook
            )
        else:
            matchable = True

        if matchable:
            result = ctx.engine.match(parent, ctx)
            parent.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.INSUFFICIENT_BALANCE:
                ctx.wal_logger.log_order_event(
                    parent.user_id,
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=parent.id,
                    symbol=ctx.symbol,
                    details={
                        "reason": f"Insufficient balance for parent order '{parent.id}'"
                    },
                )
                return

            if result.outcome == MatchOutcome.SUCCESS:
                # The call to handle fill has already placed the
                # child within the book
                return

        # Parent is not immediately matched
        ctx.orderbook.append(parent, parent.price)
        ctx.order_store.add(parent)
        ctx.order_store.add(child)

        ctx.wal_logger.log_order_event(
            parent.user_id,
            type=OrderEventType.ORDER_PLACED,
            order_id=parent.id,
            symbol=ctx.symbol,
            executed_quantity=parent.executed_quantity,
            quantity=parent.quantity,
            price=parent.price,
            side=parent.side,
        )

    def handle_filled(
        self, quantity: int, price: float, order: OTOOrder, ctx: ExecutionContext
    ) -> None:
        # Parent order
        if order.child is not None and order.executed_quantity == order.quantity:
            parent = order

            child = parent.child
            child.triggered = True

            ctx.orderbook.append(child, child.price)

            ctx.order_store.add(child)
            ctx.order_store.remove(parent)

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
        # Child order filled
        elif order.executed_quantity == order.quantity:
            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order)

    def handle_cancel(self, order: OTOOrder, ctx: ExecutionContext):
        if order.child:
            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order.child)

            ctx.wal_logger.log_order_event(
                order.user_id,
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.id,
                symbol=ctx.symbol,
                details={"reason": "Parent order cancelled."},
            )
            ctx.wal_logger.log_order_event(
                order.user_id,
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.child.id,
                symbol=ctx.symbol,
                details={"reason": "Parent order cancelled."},
            )
        elif order.parent:
            if order.triggered:
                ctx.orderbook.remove(order, order.price)
                ctx.wal_logger.log_order_event(
                    order.user_id,
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    details={},
                )
            else:
                parent = order.parent
                ctx.orderbook.remove(parent, parent.price)
                ctx.order_store.remove(parent)
                ctx.wal_logger.log_order_event(
                    order.user_id,
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=parent.id,
                    symbol=ctx.symbol,
                    details={},
                )
                ctx.wal_logger.log_order_event(
                    order.user_id,
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    details={"reason": "Parent order cancelled."},
                )

        ctx.order_store.remove(order)

    def modify(self, cmd: dict, order: OTOOrder, ctx: ExecutionContext):
        if order.parent:
            if order.triggered:
                self._modify_order(cmd, order, ctx)

            elif self._validate_modify(cmd, order, ctx):
                order.price = self._get_modified_price(cmd, order)
                ctx.wal_logger.log_order_event(
                    order.user_id,
                    type=OrderEventType.ORDER_MODIFIED,
                    order_id=order.id,
                    symbol=ctx.symbol,
                    details={"price": order.price},
                )

            return

        self._modify_order(cmd, order, ctx)
        # ctx.wal_logger.log_order_event(
        #     order.user_id,
        #     type=OrderEventType.ORDER_MODIFIED,
        #     order_id=order.id,
        #     symbol=ctx.symbol,
        #     details={"price": order.price},
        # )
