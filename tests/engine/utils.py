import uuid

from src.engine.enums import CommandType, StrategyType, OrderType
from src.engine.commands import (
    SingleOrderMeta,
    NewOCOOrderCommand,
    NewOTOOrderCommand,
    NewOTOCOOrderCommand,
)


def generate_single_order_meta(
    user_id, side, quantity, price, order_type=OrderType.LIMIT
):
    """Generates SingleOrderMeta and outputs JSON-serializable dict."""

    price_key = "limit_price" if order_type == OrderType.LIMIT else "stop_price"

    return SingleOrderMeta(
        order_id=str(uuid.uuid4()),
        user_id=user_id,
        order_type=order_type,
        side=side,
        quantity=quantity,
        **{price_key: price},
    ).model_dump(mode="json")


def create_oco_command(user_id, symbol, leg_a_meta, leg_b_meta):
    """Create OCO command and dump as JSON."""
    return NewOCOOrderCommand(
        id=str(uuid.uuid4()),
        version=1,
        type=CommandType.NEW_ORDER,
        strategy_type=StrategyType.OCO,
        symbol=symbol,
        legs=[leg_a_meta, leg_b_meta],
    ).model_dump(mode="json")


def create_oto_command(user_id, symbol, parent_meta, child_meta):
    """Create OTO command and dump as JSON."""
    return NewOTOOrderCommand(
        id=str(uuid.uuid4()),
        version=1,
        type=CommandType.NEW_ORDER,
        strategy_type=StrategyType.OTO,
        symbol=symbol,
        parent=parent_meta,
        child=child_meta,
    ).model_dump(mode="json")


def create_otoco_command(user_id, symbol, parent_meta, oco_legs_meta):
    """Create OTOCO command and dump as JSON."""
    return NewOTOCOOrderCommand(
        id=str(uuid.uuid4()),
        version=1,
        type=CommandType.NEW_ORDER,
        strategy_type=StrategyType.OTOCO,
        symbol=symbol,
        parent=parent_meta,
        oco_legs=oco_legs_meta,
    ).model_dump(mode="json")
