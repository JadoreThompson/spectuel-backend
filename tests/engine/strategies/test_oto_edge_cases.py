import pytest
from src.engine.enums import Side, OrderType
from tests.utils import create_new_order_command, create_cancel_command
from tests.engine.utils import generate_single_order_meta, create_oto_command

def test_oto_parent_partial_fill_does_not_activate_child(spot_engine, test_ctx, user_id_a, user_id_b, command_id):
    """
    Verify that a partial fill of the OTO parent order does NOT activate the child order.
    The child should only activate when the parent is FULLY filled.
    """
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # 1. Setup OTO: Buy 10 @ 90 (Parent), Sell 10 @ 100 (Child)
    balance_manager.increase_cash_balance(user_id_a, 1000, command_id)
    parent = generate_single_order_meta(user_id_a, Side.BID, 10, 90)
    child = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    spot_engine.handle_command(create_oto_command(user_id_a, symbol, parent, child))

    # 2. Partial match Parent: Sell 5 @ 90
    balance_manager.increase_asset_balance(user_id_b, 5, command_id)
    sell_cmd = create_new_order_command(user_id_b, symbol, Side.ASK, 5, 90)
    spot_engine.handle_command(sell_cmd)

    # 3. Assertions
    parent_order = test_ctx.order_store.get(parent["order_id"])
    child_order = test_ctx.order_store.get(child["order_id"])

    assert parent_order is not None
    assert parent_order.executed_quantity == 5
    
    # Child should still be inactive
    assert child_order is not None
    assert child_order.active is False
    assert 100 not in test_ctx.orderbook.asks

def test_oto_cancel_parent_with_active_child(spot_engine, test_ctx, user_id_a, user_id_b, command_id):
    """
    Verify that cancelling the parent order when the child is already active
    (which shouldn't normally happen in the current logic, but good to test)
    behaves correctly.
    """
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # 1. Setup OTO and activate child
    balance_manager.increase_cash_balance(user_id_a, 1000, command_id)
    parent = generate_single_order_meta(user_id_a, Side.BID, 10, 90)
    child = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    spot_engine.handle_command(create_oto_command(user_id_a, symbol, parent, child))

    # Fill parent to activate child
    balance_manager.increase_asset_balance(user_id_b, 10, command_id)
    fill_cmd = create_new_order_command(user_id_b, symbol, Side.ASK, 10, 90)
    spot_engine.handle_command(fill_cmd)

    child_order = test_ctx.order_store.get(child["order_id"])
    assert child_order.active is True
    assert 100 in test_ctx.orderbook.asks

    # 2. Try to cancel the parent (which is already filled and removed from store)
    # The engine should handle this gracefully.
    cancel_cmd = create_cancel_command(parent["order_id"])
    spot_engine.handle_command(cancel_cmd)

    # 3. Assertions
    # Child should still be active (cancelling a filled parent shouldn't affect child)
    assert test_ctx.order_store.get(child["order_id"]) is not None
    assert 100 in test_ctx.orderbook.asks
