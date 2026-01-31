from engine.enums import MatchOutcome, OrderType, StrategyType
from engine.events.enums import OrderEventType
from engine.execution_context import ExecutionContext
from engine.utils import get_price_key, limit_crossable, stop_crossable
from engine.orders import OTOCOOrder
from .base import StrategyBase
from .mixins import ModifyOrderMixin
from .oco_strategy import OCOStrategy


class OTOCOStrategy(ModifyOrderMixin, StrategyBase):
    def handle_new(self, cmd: dict, ctx: ExecutionContext):
        parent_dict = cmd["parent"].copy()
        child_leg_a_dict, child_leg_b_dict = cmd["oco_legs"]
        child_leg_a_dict = child_leg_a_dict.copy()
        child_leg_b_dict = child_leg_b_dict.copy()

        # Set the effective price for market orders
        if parent_dict["order_type"] == OrderType.MARKET.value:
            parent_dict["limit_price"] = ctx.orderbook.price

        parent_order = OTOCOOrder(order_dict=parent_dict)

        child_a = OTOCOOrder(
            order_dict=child_leg_a_dict,
            parent=parent_order,
        )

        child_b = OTOCOOrder(
            order_dict=child_leg_b_dict,
            parent=parent_order,
        )

        parent_order.child_a = child_a
        parent_order.child_b = child_b
        child_a.counterparty = child_b
        child_b.counterparty = child_a

        # Check if parent is matchable
        matchable = True
        if parent_dict["order_type"] == OrderType.LIMIT.value:
            matchable = limit_crossable(
                parent_dict["limit_price"], parent_order.side, ctx.orderbook
            )
        if parent_dict["order_type"] == OrderType.STOP.value:
            matchable = stop_crossable(
                parent_dict["stop_price"], parent_order.side, ctx.orderbook
            )

        command_id = ctx.cur_command_id
        if matchable:
            result = ctx.engine.match(parent_order, ctx)
            parent_order.executed_quantity = result.quantity

            if result.outcome == MatchOutcome.INSUFFICIENT_BALANCE:
                ctx.engine_logger.log_order_event(
                    parent_order.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_CANCELLED,
                    order_id=parent_order.id,
                    symbol=ctx.symbol,
                    command_id=command_id,
                    details={
                        "reason": f"Insufficient balance to place OTO parent order {parent_order.id}."
                    },
                )
                ctx.engine._release_escrow(parent_order)
                return

            if result.outcome == MatchOutcome.SUCCESS:
                ctx.engine_logger.log_order_event(
                    child_a.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_PLACED,
                    order_id=child_a.id,
                    symbol=ctx.symbol,
                    command_id=command_id,
                    order=child_a.get_order_dict(),
                )
                ctx.engine_logger.log_order_event(
                    child_b.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_PLACED,
                    order_id=child_b.id,
                    symbol=ctx.symbol,
                    command_id=command_id,
                    order=child_b.get_order_dict(),
                )

                # ctx.order_store.remove(parent_order)
                ctx.order_store.add(child_a)
                ctx.order_store.add(child_b)
                ctx.orderbook.append(child_a, child_a.price)
                ctx.orderbook.append(child_b, child_b.price)

                return

        ctx.engine_logger.log_order_event(
            parent_order.user_id,
            {"key": ctx.symbol.encode()},
            type=OrderEventType.ORDER_PLACED,
            order_id=parent_order.id,
            symbol=ctx.symbol,
            command_id=command_id,
            order=parent_order.get_order_dict(),
        )
        ctx.orderbook.append(parent_order, parent_order.price)
        ctx.order_store.add(parent_order)
        ctx.order_store.add(child_a)
        ctx.order_store.add(child_b)

    def handle_filled(
        self, quantity: int, price: float, order: OTOCOOrder, ctx: ExecutionContext
    ):
        # Parent filled: trigger OCO children
        if order.child_a and order.executed_quantity == order.quantity:
            order.active = False
            for child in (order.child_a, order.child_b):
                ctx.engine_logger.log_order_event(
                    child.user_id,
                    {"key": ctx.symbol.encode()},
                    type=OrderEventType.ORDER_PLACED,
                    order_id=child.id,
                    symbol=ctx.symbol,
                    executed_quantity=child.executed_quantity,
                    quantity=child.quantity,
                    price=child.price,
                    side=child.side,
                    command_id=ctx.cur_command_id,
                )
                child.active = True
                ctx.orderbook.append(child, child.price)
            return

        # Child filled: cancel its counterparty
        if order.counterparty:
            OCOStrategy.handle_cancel(self, order.counterparty, ctx)

    def handle_cancel(self, order: OTOCOOrder, ctx: ExecutionContext) -> None:
        if order.child_a:  # parent
            ctx.engine_logger.log_order_event(
                order.user_id,
                {"key": ctx.symbol.encode()},
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.id,
                symbol=ctx.symbol,
                details={
                    "reason": "Parent order cancelled.",
                },
                command_id=ctx.cur_command_id,
                order=order.get_order_dict(),
            )

            ctx.orderbook.remove(order, order.price)
            ctx.order_store.remove(order)
            ctx.order_store.remove(order.child_a)
            ctx.order_store.remove(order.child_b)
            ctx.engine._release_escrow(order)

            return

        # child
        counterparty = order.counterparty

        if order.active:
            ctx.engine_logger.log_order_event(
                order.user_id,
                {"key": ctx.symbol.encode()},
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.id,
                symbol=ctx.symbol,
                details={
                    "reason": "User cancelled active OCO leg.",
                },
                command_id=ctx.cur_command_id,
                order=order.get_order_dict(),
            )
            ctx.engine_logger.log_order_event(
                counterparty.user_id,
                {"key": ctx.symbol.encode()},
                type=OrderEventType.ORDER_CANCELLED,
                order_id=counterparty.id,
                symbol=ctx.symbol,
                details={
                    "reason": "User cancelled active OCO leg order.",
                },
                command_id=ctx.cur_command_id,
                order=counterparty.get_order_dict(),
            )
            ctx.orderbook.remove(order, order.price)
            ctx.orderbook.remove(counterparty, counterparty.price)
            ctx.engine._release_escrow(order)
        else:
            parent = order.parent
            ctx.engine_logger.log_order_event(
                order.user_id,
                {"key": ctx.symbol.encode()},
                type=OrderEventType.ORDER_CANCELLED,
                order_id=order.id,
                symbol=ctx.symbol,
                details={
                    "reason": "User cancelled inactive OCO leg.",
                },
                command_id=ctx.cur_command_id,
            )
            ctx.orderbook.remove(parent, parent.price)
            ctx.order_store.remove(parent)
            ctx.engine._release_escrow(parent)

        ctx.order_store.remove(order)
        ctx.order_store.remove(counterparty)

    def modify(self, cmd: dict, order: OTOCOOrder, ctx: ExecutionContext):
        if order.active:
            self._modify_order(cmd, order, ctx)
        elif self._validate_modify(cmd, order, ctx):
            new_price = self._get_modified_price(cmd, order)
            ctx.engine_logger.log_order_event(
                order.user_id,
                {"key": ctx.symbol.encode()},
                type=OrderEventType.ORDER_MODIFIED,
                order_id=order.id,
                symbol=ctx.symbol,
                **{get_price_key(order.order_type): new_price},
                command_id=ctx.cur_command_id,
            )
            order.price = new_price
