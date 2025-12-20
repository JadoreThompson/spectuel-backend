from src.engine.enums import Side

from tests.utils import create_new_order_command, create_cancel_command
from tests.engine.utils import generate_single_order_meta, create_oco_command


def test_oco_placement_and_linkage(spot_engine, test_ctx, user_id_a):
    """Verify both legs are placed and linked correctly."""
    symbol = test_ctx.symbol

    # 1. Setup Balance
    spot_engine._balance_manager.increase_asset_balance(user_id_a, symbol, 20)

    # 2. Create Command (Sell 10 @ 100, Sell 10 @ 110)
    leg_a = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    leg_b = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)
    cmd = create_oco_command(user_id_a, symbol, leg_a, leg_b)

    spot_engine.handle_command(cmd)

    # 3. Assertions
    order_a = test_ctx.order_store.get(leg_a["order_id"])
    order_b = test_ctx.order_store.get(leg_b["order_id"])

    assert order_a is not None
    assert order_b is not None
    assert order_a.counterparty.id == order_b.id
    assert order_b.counterparty.id == order_a.id

    # Both should be in the book
    assert len(list(test_ctx.orderbook.get_orders(100, Side.ASK))) == 1
    assert len(list(test_ctx.orderbook.get_orders(110, Side.ASK))) == 1


def test_oco_full_fill_cancels_other(
    spot_engine, test_ctx, user_id_a, user_id_b
):
    """Verify full fill of Leg A cancels Leg B."""
    symbol = test_ctx.symbol

    # Setup
    spot_engine._balance_manager.increase_asset_balance(user_id_a, symbol, 20)
    leg_a = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    leg_b = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)
    spot_engine.handle_command(create_oco_command(user_id_a, symbol, leg_a, leg_b))

    # Match Leg A (Buy 10 @ 100)
    spot_engine._balance_manager.increase_cash_balance(user_id_b, 1000)
    buy_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(buy_cmd)

    # Assertions
    # Leg A should be filled and removed from store
    assert test_ctx.order_store.get(leg_a["order_id"]) is None
    # Leg B should be cancelled (removed from book and store)
    assert test_ctx.order_store.get(leg_b["order_id"]) is None
    assert len(test_ctx.orderbook.asks) == 0


def test_oco_partial_fill_persistence(
    spot_engine, test_ctx, user_id_a, user_id_b
):
    """Verify partial fill of Leg A DOES NOT cancel Leg B."""
    symbol = test_ctx.symbol

    # Setup
    spot_engine._balance_manager.increase_asset_balance(user_id_a, symbol, 20)
    leg_a = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    leg_b = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)
    spot_engine.handle_command(create_oco_command(user_id_a, symbol, leg_a, leg_b))

    # Partially Match Leg A (Buy 5 @ 100)
    spot_engine._balance_manager.increase_cash_balance(user_id_b, 500)
    buy_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 5, 100)
    spot_engine.handle_command(buy_cmd)

    # Assertions
    order_a = test_ctx.order_store.get(leg_a["order_id"])
    order_b = test_ctx.order_store.get(leg_b["order_id"])

    # Leg A still exists (partial)
    assert order_a is not None
    assert order_a.executed_quantity == 5

    # Leg B MUST still exist
    assert order_b is not None
    assert 110 in test_ctx.orderbook.asks


def test_oco_manual_cancel(spot_engine, test_ctx, user_id_a):
    """Verify cancelling one leg manually cancels the other."""
    symbol = test_ctx.symbol
    
    spot_engine._balance_manager.increase_asset_balance(user_id_a, symbol, 20)
    leg_a = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    leg_b = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)
    spot_engine.handle_command(create_oco_command(user_id_a, symbol, leg_a, leg_b))

    # Cancel Leg A
    cancel_cmd = create_cancel_command(leg_a["order_id"], symbol)
    spot_engine.handle_command(cancel_cmd)

    assert test_ctx.order_store.get(leg_a["order_id"]) is None
    assert test_ctx.order_store.get(leg_b["order_id"]) is None
