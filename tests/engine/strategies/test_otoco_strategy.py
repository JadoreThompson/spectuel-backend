from src.engine.enums import Side

from tests.utils import create_new_order_command
from tests.engine.utils import generate_single_order_meta, create_otoco_command


def test_otoco_flow(spot_engine, test_ctx, user_id_a, user_id_b):
    """
    Full Flow:
    1. Place Passive Parent.
    2. Fill Parent -> Activates Child A & Child B.
    3. Fill Child A -> Cancels Child B.
    """
    symbol = test_ctx.symbol
    
    # 1. Setup
    spot_engine._balance_manager.increase_cash_balance(user_id_a, 2000)  # Buy 10 @ 90

    # Parent: Buy 10 @ 90
    parent = generate_single_order_meta(user_id_a, Side.BID, 10, 90)
    # Child A: Sell 10 @ 100 (Take Profit)
    child_a = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    # Child B: Sell 10 @ 80 (Stop Loss - mocked as Limit for simplicity here)
    child_b = generate_single_order_meta(
        user_id_a, Side.ASK, 10, 80
    )  # Wont allow Stop in asks above market, using limit logic

    cmd = create_otoco_command(user_id_a, symbol, parent, [child_a, child_b])
    spot_engine.handle_command(cmd)

    # 2. Assert Initial State
    assert 90 in test_ctx.orderbook.bids
    assert 100 not in test_ctx.orderbook.asks  # Inactive
    assert 80 not in test_ctx.orderbook.asks  # Inactive

    # 3. Fill Parent (User B sells into User A's bid)
    spot_engine._balance_manager.increase_asset_balance(user_id_b, symbol, 10)
    fill_parent_cmd = create_new_order_command(
        user_id_b, symbol, Side.ASK, 10, 90  # Limit match
    )
    spot_engine.handle_command(fill_parent_cmd)

    # Assert Activation
    assert test_ctx.order_store.get(parent["order_id"]) is None
    assert 100 in test_ctx.orderbook.asks  # Child A Active
    assert 80 in test_ctx.orderbook.asks  # Child B Active

    # 4. Fill Child A (User B buys 10 @ 100)
    spot_engine._balance_manager.increase_cash_balance(user_id_b, 1000)
    fill_child_a_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(fill_child_a_cmd)

    # Assert Final OCO Logic
    assert test_ctx.order_store.get(child_a["order_id"]) is None  # Filled
    assert test_ctx.order_store.get(child_b["order_id"]) is None  # Cancelled
    assert 80 not in test_ctx.orderbook.asks
