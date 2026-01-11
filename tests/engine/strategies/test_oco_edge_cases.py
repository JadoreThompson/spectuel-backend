import pytest
from src.engine.enums import Side
from tests.utils import create_new_order_command, create_cancel_command
from tests.engine.utils import generate_single_order_meta, create_oco_command


def test_oco_modify_leg_price(spot_engine, test_ctx, user_id_a, command_id):
    """Verify modifying the price of one OCO leg works and keeps the linkage."""
    symbol = test_ctx.symbol
    balance_manager = spot_engine._balance_manager

    # 1. Setup OCO
    balance_manager.increase_asset_balance(user_id_a, 20, command_id)
    leg_a = generate_single_order_meta(user_id_a, Side.ASK, 10, 100)
    leg_b = generate_single_order_meta(user_id_a, Side.ASK, 10, 110)
    spot_engine.handle_command(create_oco_command(user_id_a, symbol, leg_a, leg_b))

    # 2. Modify Leg A price: 100 -> 105
    from engine.commands import ModifyOrderCommand, CommandType
    mod_cmd = ModifyOrderCommand(
        id=command_id,
        type=CommandType.MODIFY_ORDER,
        order_id=leg_a["order_id"],
        limit_price=105.0,
    ).model_dump(mode="json")
    spot_engine.handle_command(mod_cmd)

    # 3. Assertions
    order_a = test_ctx.order_store.get(leg_a["order_id"])
    order_b = test_ctx.order_store.get(leg_b["order_id"])

    assert order_a.price == 105.0
    assert 105 in test_ctx.orderbook.asks
    assert 100 not in test_ctx.orderbook.asks
    
    # Linkage should still be intact
    assert order_a.counterparty.id == order_b.id
    assert order_b.counterparty.id == order_a.id
