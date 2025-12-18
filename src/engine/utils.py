from engine.enums import OrderType, Side
from engine.orderbook import OrderBook


def get_price_key(ot: OrderType) -> str | None:
    ot = OrderType(ot)
    key = {
        OrderType.MARKET: "price",
        OrderType.LIMIT: "limit_price",
        OrderType.STOP: "stop_price",
    }

    return key.get(ot)


def limit_crossable(price: float, side: Side, ob: OrderBook) -> bool:
    return (side == Side.BID and ob.best_ask is not None and price >= ob.best_ask) or (
        side == Side.ASK and ob.best_bid is not None and price <= ob.best_bid
    )


def stop_crossable(price: float, side: Side, ob: OrderBook) -> bool:
    return (side == Side.BID and ob.best_ask is not None and price <= ob.best_ask) or (
        side == Side.ASK and ob.best_bid is not None and price >= ob.best_bid
    )


def get_symbol_balance_hkey(symbol: str) -> str:
    return f"{symbol}.balances"


def get_symbol_escrows_hkey(symbol: str) -> str:
    return f"{symbol}.escrows"
