from enum import Enum


class Side(str, Enum):
    BID = "bid"
    ASK = "ask"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class TimeInForce(Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class StrategyType(str, Enum):
    SINGLE = "SINGLE"
    OCO = "OCO"
    OTO = "OTO"
    OTOCO = "OTOCO"


class LiquidityRole(Enum):
    MAKER = "MAKER"
    TAKER = "TAKER"


class InstrumentEventType(Enum):
    PRICE = "price"
    TRADES = "trades"
    ORDERBOOK = "orderbook"


class TransactionType(Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRADE = "TRADE"
    ESCROW = "ESCROW"


class OrderStatus(Enum):
    PENDING = "pending"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class UserStatus(Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class InstrumentStatus(Enum):
    TRADABLE = "TRADABLE"
    DELISTED = "DELISTED"


class TimeFrame(Enum):
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    def to_interval(self) -> str:
        """Convert shorthand timeframe into a PostgreSQL interval string."""
        unit = self.value[-1]
        amount = int(self.value[:-1])

        if unit == "m":
            return f"{amount} minute"
        elif unit == "h":
            return f"{amount} hour"
        elif unit == "d":
            return f"{amount} day"
        else:
            raise ValueError(f"Unsupported timeframe unit: {unit}")
