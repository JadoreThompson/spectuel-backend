from src.engine.enums import Side, OrderType

from tests.utils import create_new_order_command, create_cancel_command
from tests.engine.utils import generate_single_order_meta, create_oto_command


def test_oto_passive_parent_placement(spot_engine, test_ctx, user_id_a):
    """
    Verify that if Parent does NOT cross the spread, it goes to book,
    and Child remains inactive (not in book).
    """
    # 1. Setup: Clean book.
    symbol = test_ctx.symbol

    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)

    # 2. Parent: Buy 10 @ 90 (Passive). Child: Sell 10 @ 100.
    parent = generate_single_order_meta(user_id_a, Side.BID, 10, 90)
    child = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    cmd = create_oto_command(user_id_a, symbol, parent, child)

    spot_engine.handle_command(cmd)

    # 3. Assertions
    parent_order = test_ctx.order_store.get(parent["order_id"])
    child_order = test_ctx.order_store.get(child["order_id"])

    assert parent_order is not None
    assert child_order is not None

    # Parent should be in book
    assert 90 in test_ctx.orderbook.bids

    # Child should NOT be in book yet (inactive)
    assert 100 not in test_ctx.orderbook.asks
    assert child_order.triggered is False


def test_oto_delayed_activation(spot_engine, test_ctx, user_id_a, user_id_b):
    """Verify Child activates when Passive Parent is filled later."""
    symbol = test_ctx.symbol
    
    # Setup Passive Parent
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    parent = generate_single_order_meta(user_id_a, Side.BID, 10, 90)
    child = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)  # Sell @ 100
    spot_engine.handle_command(create_oto_command(user_id_a, symbol, parent, child))

    # Verify Child Inactive
    child_order = test_ctx.order_store.get(child["order_id"])
    assert child_order.triggered is False

    # Action: User B Sells into Parent (Market Sell 10)
    spot_engine._balance_manager.increase_asset_balance(user_id_b, symbol, 10)
    fill_cmd = create_new_order_command(
        user_id_b, symbol, Side.ASK, 10, 90, order_type=OrderType.LIMIT
    )
    spot_engine.handle_command(fill_cmd)

    # Assertions
    # Parent filled/removed
    assert test_ctx.order_store.get(parent["order_id"]) is None

    # Child Activated
    child_order = test_ctx.order_store.get(child["order_id"])
    assert child_order.triggered is True
    # Child is a Sell Limit @ 100, should be in Asks
    assert 100 in test_ctx.orderbook.asks


def test_oto_immediate_match_activates_child(
    spot_engine, test_ctx, user_id_a, user_id_b, symbol
):
    """Verify immediate parent match activates child immediately."""
    # Setup: User B provides liquidity (Sell Limit @ 100)
    spot_engine._balance_manager.increase_asset_balance(user_id_b, symbol, 10)
    maker_cmd = create_new_order_command(user_id_b, symbol, Side.ASK, 10, 100)
    spot_engine.handle_command(maker_cmd)

    # Action: User A sends OTO. Parent = Buy Market (Immediate Fill). Child = Sell @ 110.
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1100)
    parent = generate_single_order_meta(
        user_id_a, Side.BID, 10, 110, order_type=OrderType.LIMIT
    )
    child = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)

    oto_cmd = create_oto_command(user_id_a, symbol, parent, child)
    spot_engine.handle_command(oto_cmd)

    # Assertions
    # Parent was Market, matched immediately, gone from store
    assert test_ctx.order_store.get(parent["order_id"]) is None

    # Child (Sell @ 110) should be in book immediately
    assert 110 in test_ctx.orderbook.asks
    child_order = test_ctx.order_store.get(child["order_id"])
    assert child_order.triggered is True


def test_oto_cancel_child_cancels_parent(spot_engine, test_ctx, user_id_a, symbol):
    """
    Verify upwards cascading cancellation:
    Cancelling the inactive child should cancel the pending parent.
    """
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 1000)
    parent = generate_single_order_meta(user_id_a, Side.BID, 10, 90)
    child = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)
    spot_engine.handle_command(create_oto_command(user_id_a, symbol, parent, child))

    # Action: Cancel Child
    cancel_cmd = create_cancel_command(child["order_id"], symbol)
    spot_engine.handle_command(cancel_cmd)

    # Assertions
    assert test_ctx.order_store.get(parent["order_id"]) is None
    assert test_ctx.order_store.get(child["order_id"]) is None
    assert 90 not in test_ctx.orderbook.bids
