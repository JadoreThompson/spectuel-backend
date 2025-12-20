import pytest
from src.engine.enums import Side
from tests.utils import create_new_order_command, create_cancel_command


def test_cancel_single_order(spot_engine, test_ctx, user_id_a):
    """
    Scenario: Place order, Cancel order.
    Result: Order removed from Book and Store.
    """
    symbol = test_ctx.symbol

    # 1. Place
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    place_cmd = create_new_order_command(user_id_a, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(place_cmd)

    assert test_ctx.orderbook.best_bid == 100
    assert len(test_ctx.order_store._orders) == 1

    # 2. Cancel
    cancel_cmd = create_cancel_command(place_cmd["order_id"], symbol)
    spot_engine.handle_command(cancel_cmd)

    # 3. Assert
    assert test_ctx.orderbook.best_bid is None
    assert len(test_ctx.orderbook.bids) == 0
    assert test_ctx.order_store.get(place_cmd["order_id"]) is None


def test_cancel_partial_fill_order(spot_engine, test_ctx, user_id_a, user_id_b):
    """
    Scenario: Order A (10) partially filled by Order B (5). Cancel remainder of A.
    Result: A removed.
    """
    symbol = test_ctx.symbol

    # 1. Place A (10 @ 100)
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    spot_engine._balance_manager.increase_asset_balance(user_id_b, symbol, 10)

    cmd_a = create_new_order_command(user_id_a, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(cmd_a)

    # 2. Place B (5 @ 100 - match)
    cmd_b = create_new_order_command(user_id_b, symbol, Side.ASK, 5, 100)
    spot_engine.handle_command(cmd_b)

    # Check Partial State
    order_a = test_ctx.order_store.get(cmd_a["order_id"])
    assert order_a.executed_quantity == 5
    assert test_ctx.orderbook.best_bid == 100

    # 3. Cancel A
    cancel_cmd = create_cancel_command(cmd_a["order_id"], symbol)
    spot_engine.handle_command(cancel_cmd)

    # 4. Assert
    assert test_ctx.orderbook.best_bid is None
    assert test_ctx.order_store.get(cmd_a["order_id"]) is None


def test_cancel_non_existent_order(spot_engine, test_ctx):
    """
    Scenario: Send cancel for random ID.
    Result: No crash, state unchanged.
    """
    symbol = test_ctx.symbol
    
    import uuid

    random_id = str(uuid.uuid4())

    cancel_cmd = create_cancel_command(random_id, symbol)

    # Should simply return safely
    spot_engine.handle_command(cancel_cmd)

    assert len(test_ctx.order_store._orders) == 0
