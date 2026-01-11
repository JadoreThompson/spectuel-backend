import pytest
from src.engine.enums import Side, StrategyType, OrderType
from src.engine.config import SYSTEM_USER_ID
from tests.utils import create_new_order_command, create_cancel_command

def test_maker_insufficient_balance_cancels_maker(spot_engine, test_ctx, user_id_a, user_id_b, command_id, mocker):
    """
    Scenario: 
    1. Maker (User A) places an ASK order.
    2. Maker's balance is reduced externally (e.g., by another trade or withdrawal).
    3. Taker (User B) places a matching BID order.
    Result: Maker's order is cancelled due to insufficient balance, and Taker's order remains or is partially filled.
    """
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # 1. Maker places ASK order for 10 units @ 100
    balance_manager.increase_asset_balance(user_id_a, 10, command_id)
    ask_cmd = create_new_order_command(user_id_a, symbol, Side.ASK, 10, 100)
    spot_engine.handle_command(ask_cmd)

    # 2. Reduce Maker's balance to 5 units
    balance_manager.decrease_asset_balance(user_id_a, 5, command_id)
    assert balance_manager.get_available_asset_balance(user_id_a) == 5

    # Spy on the cancel handler for the maker
    cancel_spy = mocker.spy(
        spot_engine._strategy_handlers[StrategyType.SINGLE], "handle_cancel"
    )

    # 3. Taker places BID order for 10 units @ 100
    balance_manager.increase_cash_balance(user_id_b, 1000, command_id)
    bid_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(bid_cmd)

    # Assertions
    # Maker's order should be cancelled
    assert test_ctx.order_store.get(ask_cmd["order_id"]) is None
    cancel_spy.assert_called()
    
    # Taker's order should still be in the book (since maker was cancelled)
    # Actually, in the current implementation, if maker is cancelled, it continues to the next maker or breaks.
    # Since there's no other maker, the taker order should be placed in the book.
    assert test_ctx.orderbook.best_bid == 100
    assert test_ctx.order_store.get(bid_cmd["order_id"]) is not None

def test_escrow_release_on_full_cancel(spot_engine, test_ctx, user_id_a, command_id):
    """Verify escrow is fully released when an order is cancelled."""
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # 1. Place BID order with escrow
    balance_manager.increase_cash_balance(user_id_a, 1000, command_id)
    # Manual escrow to simulate API behavior
    balance_manager.increase_cash_escrow(user_id_a, 1000, command_id)
    
    place_cmd = create_new_order_command(user_id_a, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(place_cmd)

    assert balance_manager.get_cash_escrow(user_id_a) == 1000
    assert balance_manager.get_available_cash_balance(user_id_a) == 0

    # 2. Cancel order
    cancel_cmd = create_cancel_command(place_cmd["order_id"])
    spot_engine.handle_command(cancel_cmd)

    # 3. Assert escrow released
    assert balance_manager.get_cash_escrow(user_id_a) == 0
    assert balance_manager.get_available_cash_balance(user_id_a) == 1000

def test_system_user_balance_bypass(spot_engine, test_ctx, user_id_b, command_id):
    """Verify SYSTEM_USER_ID can place orders without balance checks."""
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # SYSTEM_USER_ID places an ASK order without having any asset balance
    ask_cmd = create_new_order_command(SYSTEM_USER_ID, symbol, Side.ASK, 10, 100)
    spot_engine.handle_command(ask_cmd)

    assert test_ctx.orderbook.best_ask == 100
    assert test_ctx.order_store.get(ask_cmd["order_id"]) is not None

    # Taker matches with SYSTEM_USER_ID
    balance_manager.increase_cash_balance(user_id_b, 1000, command_id)
    bid_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(bid_cmd)

    # Assertions
    assert test_ctx.orderbook.best_ask is None
    assert balance_manager.get_available_asset_balance(user_id_b) == 10
