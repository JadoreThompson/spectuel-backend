from engine.config import SYSTEM_USER_ID
from engine.enums import (
    MatchOutcome,
    LiquidityRole,
    OrderType,
    Side,
    StrategyType,
    CommandType,
)
from engine.events import OrderEventType
from engine.events.enums import CommandEventType, InstrumentEventType
from engine.execution_context import ExecutionContext
from engine.loggers import EngineLogger
from engine.orderbook import OrderBook
from engine.services.balance_manager import BalanceManager
from engine.stores import OrderStore
from engine.strategies import (
    SingleOrderStrategy,
    OCOStrategy,
    OTOStrategy,
    OTOCOStrategy,
)
from engine.strategies import StrategyBase
from engine.types import MatchResult
from engine.orders import Order
from .base import EngineBase


class SpotEngine(EngineBase):
    def __init__(
        self,
        symbol: str,
        ctx: ExecutionContext | None = None,
        logger: EngineLogger | None = None,
    ) -> None:
        self._strategy_handlers: dict[StrategyType, StrategyBase] = {
            StrategyType.SINGLE: SingleOrderStrategy(),
            StrategyType.OCO: OCOStrategy(),
            StrategyType.OTO: OTOStrategy(),
            StrategyType.OTOCO: OTOCOStrategy(),
        }

        self._ctx = ctx or ExecutionContext(
            engine=self,
            orderbook=OrderBook(),
            order_store=OrderStore(),
            symbol=symbol,
            engine_logger=logger,
        )

        self._balance_manager = BalanceManager(symbol, self._ctx.engine_logger)

    @property
    def symbol(self) -> str:
        return self._ctx.symbol

    @property
    def ctx(self) -> ExecutionContext:
        return self._ctx

    @property
    def balance_manager(self) -> BalanceManager:
        return self._balance_manager

    def handle_command(self, cmd: dict) -> None:
        """Main entry point for processing all incoming commands."""
        handlers = {
            CommandType.NEW_ORDER: self._handle_new_order,
            CommandType.CANCEL_ORDER: self._handle_cancel_order,
            CommandType.MODIFY_ORDER: self._handle_modify_order,
        }
        handler = handlers.get(cmd["type"])
        if handler is not None:
            self._ctx.cur_command_id = cmd["id"]
            self._ctx.engine_logger.log_command_event(
                type=CommandEventType.COMMAND_RECEIVED,
                command=cmd,
            )
            handler(cmd)
            self._ctx.engine_logger.log_command_event(
                type=CommandEventType.COMMAND_PROCESSED,
                command_id=self._ctx.cur_command_id,
            )

    def _handle_new_order(self, cmd: dict) -> None:
        """
        Receives the dictionary form of one of the
        NewOrderCommand commands and routes to the appropriate
        strategy for handling.

        Args:
            cmd (dict): dictionary form of a NewOrderCommand
        """
        strategy = self._strategy_handlers.get(cmd["strategy_type"])
        if strategy is None:
            return

        strategy.handle_new(cmd, self._ctx)

    def _handle_cancel_order(self, cmd: dict) -> None:
        """
        Receives the dictionary form of the CancelOrderCommand
        commands and routes to the appropriate strategy for
        handling.

        Args:
            cmd (dict): dictionary form of a CancelOrderCommand
        """
        order = self._ctx.order_store.get(cmd["order_id"])
        if order is None:
            return

        strategy = self._strategy_handlers.get(order.strategy_type)
        if strategy is None:
            return

        strategy.handle_cancel(order, self._ctx)

    def _handle_modify_order(self, cmd: dict) -> None:
        """
        Receives the dictionary form of the ModifyOrderCommand
        commands and routes to the appropriate strategy for
        handling.

        Args:
            cmd (dict): dictionary form of a ModifyOrderCommand
        """
        order = self._ctx.order_store.get(cmd["order_id"])
        if order is None:
            return

        strategy = self._strategy_handlers.get(order.strategy_type)
        if strategy is None:
            return

        strategy.modify(cmd, order, self._ctx)

    def match(self, taker_order: Order, ctx: ExecutionContext) -> MatchResult:
        """
        Public method for strategies to submit an order for immediate matching.
        This fulfills the EngineProtocol requirement cleanly.
        """
        if not self._check_sufficient_balance(
            taker_order, taker_order.quantity, taker_order.price, ctx.symbol
        ):
            handler = self._strategy_handlers[taker_order.strategy_type]
            handler.handle_cancel(taker_order, ctx)
            return MatchResult(
                outcome=MatchOutcome.INSUFFICIENT_BALANCE, quantity=0, price=None
            )

        return self._match(taker_order, ctx)

    # TODO: Every match must check both the taker and maker if they have
    # sufficient balance
    def _match(self, taker_order: Order, ctx: ExecutionContext) -> MatchResult:
        opposite_side = Side.ASK if taker_order.side == Side.BID else Side.BID
        ob = ctx.orderbook
        prev_best_price = None

        while taker_order.executed_quantity < taker_order.quantity:
            best_price = ob.best_ask if opposite_side is Side.ASK else ob.best_bid
            if best_price is None or prev_best_price == best_price:
                break

            for maker_order in ob.get_orders(best_price, opposite_side):
                if taker_order.executed_quantity >= taker_order.quantity:
                    break

                unfilled_maker_qty = (
                    maker_order.quantity - maker_order.executed_quantity
                )
                trade_qty = min(
                    unfilled_maker_qty,
                    taker_order.quantity - taker_order.executed_quantity,
                )

                if not self._check_sufficient_balance(
                    maker_order, trade_qty, best_price, ctx.symbol
                ):
                    handler = self._strategy_handlers[maker_order.strategy_type]
                    handler.handle_cancel(maker_order, ctx)
                    continue

                self._process_trade(
                    taker_order, maker_order, trade_qty, best_price, ctx
                )

            prev_best_price = best_price

        if taker_order.executed_quantity == taker_order.quantity:
            return MatchResult(
                MatchOutcome.SUCCESS, taker_order.quantity, prev_best_price
            )
        if taker_order.executed_quantity == 0:
            return MatchResult(MatchOutcome.FAILURE, 0, None)
        return MatchResult(
            MatchOutcome.PARTIAL, taker_order.executed_quantity, prev_best_price
        )

    def _check_sufficient_balance(
        self, order: Order, quantity: float, price: float, symbol: str
    ) -> bool:
        """
        Checks if the user has sufficient balance to execute this trade.

        Args:
            order (Order): Order being used in the trade.
            quantity (float): Quantity being matched
            price (float): _description_

        Returns:
            bool:
                - True: Sufficient balance.
                - False: Insufficient balance.
        """
        if order.user_id == SYSTEM_USER_ID:
            return True

        if order.order_type == OrderType.MARKET:
            # TODO: Implement balance checks
            raise NotImplementedError

        if order.side == Side.ASK:
            return quantity <= self._balance_manager.get_available_asset_balance(
                order.user_id
            )

        trade_value = quantity * price
        return trade_value <= self._balance_manager.get_available_cash_balance(
            order.user_id
        )

    def _process_trade(
        self,
        taker_order: Order,
        maker_order: Order,
        quantity: float,
        price: float,
        ctx: ExecutionContext,
    ) -> None:
        """
        Handles the logic for a single trade event: updating quantities,
        notifying strategies, and removing filled orders.
        """
        command_id = ctx.cur_command_id
        taker_trade_event_id = self._ctx.engine_logger.generate_id()
        maker_trade_event_id = self._ctx.engine_logger.generate_id()
        self._ctx.engine_logger.log_trade_event(
            taker_order.user_id,
            id=taker_trade_event_id,
            type=InstrumentEventType.NEW_TRADE,
            order_id=taker_order.id,
            symbol=ctx.symbol,
            quantity=quantity,
            price=price,
            role=LiquidityRole.TAKER,
            command_id=command_id,
        )
        self._ctx.engine_logger.log_trade_event(
            maker_order.user_id,
            id=maker_trade_event_id,
            type=InstrumentEventType.NEW_TRADE,
            order_id=maker_order.id,
            symbol=ctx.symbol,
            quantity=quantity,
            price=price,
            role=LiquidityRole.MAKER,
            command_id=command_id,
        )

        # Handle fill event
        prev_taker_exec_quantity = taker_order.executed_quantity
        prev_maker_exec_quantity = maker_order.executed_quantity

        taker_exec_quantity = prev_taker_exec_quantity + quantity
        maker_exec_quantity = prev_maker_exec_quantity + quantity

        self._log_fill_event(taker_order, price, taker_exec_quantity, ctx.symbol)
        self._log_fill_event(maker_order, price, maker_exec_quantity, ctx.symbol)

        taker_order.executed_quantity = taker_exec_quantity
        maker_order.executed_quantity = maker_exec_quantity

        taker_strategy = self._strategy_handlers[taker_order.strategy_type]
        maker_strategy = self._strategy_handlers[maker_order.strategy_type]
        taker_strategy.handle_filled(quantity, price, taker_order, ctx)
        maker_strategy.handle_filled(quantity, price, maker_order, ctx)

        if maker_order.executed_quantity == maker_order.quantity:
            ctx.orderbook.remove(maker_order, price)
            ctx.order_store.remove(maker_order)

        # Handle balance event
        if prev_maker_exec_quantity == 0:
            if maker_order.side == Side.BID:
                self._balance_manager.increase_cash_escrow(
                    maker_order.user_id,
                    maker_order.quantity * maker_order.price,
                    command_id,
                )
            else:
                self._balance_manager.increase_asset_escrow(
                    maker_order.user_id, maker_order.quantity, command_id
                )

        if prev_taker_exec_quantity == 0:
            if taker_order.side == Side.BID:
                self._balance_manager.increase_cash_escrow(
                    taker_order.user_id,
                    taker_order.quantity * taker_order.price,
                    command_id,
                )
            else:
                self._balance_manager.increase_asset_escrow(
                    taker_order.user_id, taker_order.quantity, command_id
                )

        if taker_order.side == Side.BID:
            self._balance_manager.settle_bid(
                taker_order.user_id,
                quantity,
                price,
                command_id,
                trade_event_id=taker_trade_event_id,
            )
            self._balance_manager.settle_ask(
                maker_order.user_id,
                quantity,
                price,
                command_id,
                trade_event_id=maker_trade_event_id,
            )
        else:
            self._balance_manager.settle_ask(
                taker_order.user_id,
                quantity,
                price,
                command_id,
                trade_event_id=taker_trade_event_id,
            )
            self._balance_manager.settle_bid(
                maker_order.user_id,
                quantity,
                price,
                command_id,
                trade_event_id=maker_trade_event_id,
            )

    def _log_fill_event(
        self, order: Order, price: float, executed_quantity, symbol: str
    ) -> None:
        etype = (
            OrderEventType.ORDER_FILLED
            if order.executed_quantity == order.quantity
            else OrderEventType.ORDER_PARTIALLY_FILLED
        )
        self._ctx.engine_logger.log_order_event(
            order.user_id,
            {"key": symbol},
            type=etype,
            order_id=order.id,
            symbol=symbol,
            executed_quantity=executed_quantity,
            quantity=order.quantity,
            price=price,
            command_id=self._ctx.cur_command_id,
        )

    def _release_escrow(self, order: Order) -> None:
        """
        Releases the remaining quantity for an order if the executed
        quantity is greater than 0.

        Args:
            order (Order): The order to release escrow for.
        """
        command_id = self._ctx.cur_command_id

        if order.side == Side.BID:
            unfilled_qty = order.quantity - order.executed_quantity
            if unfilled_qty > 0:
                self._balance_manager.decrease_cash_escrow(
                    order.user_id, unfilled_qty * order.price, command_id
                )
        else:
            unfilled_qty = order.quantity - order.executed_quantity
            if unfilled_qty > 0:
                self._balance_manager.decrease_asset_escrow(
                    order.user_id, unfilled_qty, command_id
                )
