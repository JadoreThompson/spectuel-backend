from src.engine.enums import Side, StrategyType

from tests.utils import create_new_order_command


def test_full_match(spot_engine, test_ctx, user_id_a, user_id_b):
    symbol = test_ctx.symbol
    # User A has 10 units of the asset.
    balance_manager = spot_engine._balance_manager
    balance_manager.increase_asset_balance(user_id_a, symbol, 10)
    ask_cmd = create_new_order_command(user_id_a, symbol, Side.ASK, 10, 100)
    spot_engine.handle_command(ask_cmd)

    # Only order in the book
    assert test_ctx.orderbook.best_ask == 100

    # Set initial cash balance. No escrow as it's a limit order
    # so we can't apply any escrow yet.
    balance_manager.increase_cash_balance(user_id_b, 1000)
    bid_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(bid_cmd)

    # Order book should be empty now.
    assert test_ctx.orderbook.best_ask is None
    assert test_ctx.orderbook.best_bid is None
    assert len(test_ctx.order_store._orders) == 0

    # User A (seller): starts with 10 asset, 0 cash. Ends with 0 asset, 1000 cash.
    assert balance_manager.get_available_cash_balance(user_id_a) == 1000
    assert balance_manager.get_available_asset_balance(user_id_a, symbol) == 0

    # User B (buyer): starts with 1000 cash, 0 asset. Ends with 0 cash, 10 asset.
    assert balance_manager.get_available_cash_balance(user_id_b) == 0
    assert balance_manager.get_available_asset_balance(user_id_b, symbol) == 10


def test_partial_match(spot_engine, test_ctx, user_id_a, user_id_b):
    symbol = test_ctx.symbol    
    balance_manager = spot_engine._balance_manager

    balance_manager.increase_asset_balance(user_id_a, symbol, 5)
    ask_cmd = create_new_order_command(user_id_a, symbol, Side.ASK, 5, 100)
    spot_engine.handle_command(ask_cmd)

    balance_manager.increase_cash_balance(user_id_b, 1000)
    bid_cmd = create_new_order_command(user_id_b, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(bid_cmd)

    assert test_ctx.orderbook.best_ask is None
    assert test_ctx.orderbook.best_bid == 100
    assert len(test_ctx.order_store._orders) == 1

    remaining_order = test_ctx.order_store.get(bid_cmd["order_id"])
    assert remaining_order is not None
    assert remaining_order.user_id == user_id_b
    assert remaining_order.quantity == 10
    assert remaining_order.executed_quantity == 5

    assert balance_manager.get_available_cash_balance(user_id_a) == 500
    assert balance_manager.get_available_asset_balance(user_id_a, symbol) == 0

    assert balance_manager.get_cash_escrow(user_id_b) == 500
    assert balance_manager.get_cash_balance(user_id_b) == 500
    assert balance_manager.get_available_cash_balance(user_id_b) == 0
    assert balance_manager.get_available_asset_balance(user_id_b, symbol) == 5


def test_insufficient_balance_cancels_order(
    spot_engine, test_ctx, user_id_a, user_id_b, mocker
):
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # Set User A's cash balance to be exactly 500.
    balance_manager.increase_asset_balance(user_id_b, symbol, 10)
    ask_cmd = create_new_order_command(user_id_b, symbol, Side.ASK, 10, 100)
    spot_engine.handle_command(ask_cmd)

    initial_balance = balance_manager.get_available_cash_balance(user_id_a)
    balance_manager.decrease_cash_balance(user_id_a, initial_balance - 500)
    assert balance_manager.get_available_cash_balance(user_id_a) == 500

    # Spy on the cancel handler to confirm it's called for the right reason.
    cancel_spy = mocker.spy(
        spot_engine._strategy_handlers[StrategyType.SINGLE], "handle_cancel"
    )

    # Action: User A places an order they cannot afford.
    bid_cmd = create_new_order_command(user_id_a, symbol, Side.BID, 10, 100)
    spot_engine.handle_command(bid_cmd)

    # Assertions
    assert test_ctx.orderbook.best_bid is None
    assert test_ctx.order_store.get(bid_cmd["order_id"]) is None
    # The cancel handler should have been invoked by the engine.
    cancel_spy.assert_called_once()
