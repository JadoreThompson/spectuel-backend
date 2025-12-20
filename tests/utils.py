import uuid

from src.engine.commands import NewSingleOrderCommand, CancelOrderCommand
from src.engine.enums import CommandType, StrategyType, Side, OrderType


def create_new_order_command(
    user_id: str,
    symbol: str,
    side: Side,
    quantity: int,
    price: float,
    order_type: OrderType = OrderType.LIMIT,
    order_id: str = None,
    details: dict = None,
) -> dict:
    """Helper to create a single order command dictionary with the correct flat structure."""
    price_key = "limit_price" if order_type == OrderType.LIMIT else "stop_price"

    return NewSingleOrderCommand(
        type=CommandType.NEW_ORDER,
        strategy_type=StrategyType.SINGLE,
        order_id=order_id or str(uuid.uuid4()),
        user_id=user_id,
        order_type=order_type,
        side=side,
        symbol=symbol,
        quantity=quantity,
        details=details,
        **{price_key: price},  # because price_key is dynamic
    ).model_dump(mode="json")


def create_cancel_command(order_id: str, symbol: str) -> dict:
    """Helper to create a cancel order command dictionary."""
    return CancelOrderCommand(
        type=CommandType.CANCEL_ORDER,
        order_id=order_id,
        symbol=symbol,
    ).model_dump(mode="json")
