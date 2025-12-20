import pytest
from src.engine.enums import Side, OrderType, StrategyType
from tests.utils import create_new_order_command
from src.engine.commands import ModifyOrderCommand, CommandType


def create_modify_command(order_id, limit_price=None, stop_price=None):
    return ModifyOrderCommand(
        id=order_id,  # Reusing UUID for cmd id for simplicity, or generate new
        type=CommandType.MODIFY_ORDER,
        order_id=order_id,
        limit_price=limit_price,
        stop_price=stop_price,
    ).model_dump(mode="json")


def test_modify_order_limit_price_success(spot_engine, test_ctx, user_id_a):
    """
    Scenario: User places Limit Bid @ 100. Modifies to 101.
    Result: Order stays in book, price updates to 101.
    """
    symbol = test_ctx.symbol

    # 1. Place Initial Order
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    cmd = create_new_order_command(user_id_a, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(cmd)

    assert test_ctx.orderbook.best_bid == 100
    order_id = cmd["order_id"]

    # 2. Modify Order
    mod_cmd = create_modify_command(order_id, limit_price=101.0)
    spot_engine.handle_command(mod_cmd)

    # 3. Assertions
    # Old level gone
    assert 100 not in test_ctx.orderbook.bids
    # New level exists
    assert test_ctx.orderbook.best_bid == 101
    # Store updated
    order = test_ctx.order_store.get(order_id)
    assert order.price == 101.0


def test_modify_order_reject_crossing_spread(
    spot_engine, test_ctx, user_id_a, user_id_b
):
    """
    Scenario:
    1. User A Bids @ 100.
    2. User B Asks @ 105.
    3. User A modifies Bid to 106 (Crosses Spread).
    Result: Modification rejected. Price stays 100.
    """
    symbol = test_ctx.symbol

    # Setup
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    spot_engine._balance_manager.increase_asset_balance(user_id_b, symbol, 10)

    cmd_a = create_new_order_command(user_id_a, symbol, Side.BID, 10, 100)
    cmd_b = create_new_order_command(user_id_b, symbol, Side.ASK, 10, 105)

    spot_engine.handle_command(cmd_a)
    spot_engine.handle_command(cmd_b)

    assert test_ctx.orderbook.best_bid == 100
    assert test_ctx.orderbook.best_ask == 105

    # Modify Bid 100 -> 106 (Would match immediately)
    # The current engine implementation REJECTS modifications that would match.
    mod_cmd = create_modify_command(cmd_a["order_id"], limit_price=106.0)
    spot_engine.handle_command(mod_cmd)

    # Assertions: Modification Failed
    assert test_ctx.orderbook.best_bid == 100
    order = test_ctx.order_store.get(cmd_a["order_id"])
    assert order.price == 100.0


def test_modify_stop_order(spot_engine, test_ctx, user_id_a):
    """Verify modifying a stop price works."""
    symbol = test_ctx.symbol

    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    cmd = create_new_order_command(
        user_id_a, symbol, Side.BID, 10, 110, order_type=OrderType.STOP
    )
    spot_engine.handle_command(cmd)

    order = test_ctx.order_store.get(cmd["order_id"])
    assert order.price == 110

    # Modify
    mod_cmd = create_modify_command(cmd["order_id"], stop_price=115.0)
    spot_engine.handle_command(mod_cmd)

    assert order.price == 115.0
