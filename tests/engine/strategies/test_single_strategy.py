import pytest
from tests.utils import create_new_order_command, create_cancel_command
from src.engine.enums import Side


def test_single_order_placed_in_book(spot_engine, test_ctx, user_id_a):
    """
    Visualize Flow:
    1. User wants to place a BID for 10 units @ 99 ($990 total).
    2. Test simulates the API by escrowing $990 from the user's cash balance.
    3. Engine receives the command. The order doesn't cross the spread (empty book).
    4. The engine places the order on the book without matching.
    5. Assert the order exists on the book and in the store.
    """
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # Setup: User has funds and the API escrows them.
    balance_manager.increase_cash_escrow(user_id_a, 990)  # 10 * 99

    cmd = create_new_order_command(user_id_a, symbol, Side.BID, 10, 99)
    spot_engine.handle_command(cmd)

    assert test_ctx.orderbook.best_bid == 99
    order = test_ctx.order_store.get(cmd["order_id"])
    assert order is not None
    assert order.price == 99


def test_single_order_cancel(spot_engine, test_ctx, user_id_a):
    symbol = test_ctx.symbol

    balance_manager = spot_engine._balance_manager

    # Setup: Place an order first, including escrow.
    balance_manager.increase_cash_escrow(user_id_a, 990)
    place_cmd = create_new_order_command(user_id_a, symbol, Side.BID, 10, 99)
    spot_engine.handle_command(place_cmd)

    assert test_ctx.orderbook.best_bid == 99

    # Action: Cancel the order.
    cancel_cmd = create_cancel_command(place_cmd["order_id"], symbol)
    spot_engine.handle_command(cancel_cmd)

    # Assertions
    assert test_ctx.orderbook.best_bid is None
    assert test_ctx.order_store.get(place_cmd["order_id"]) is None
