from enum import Enum


from enum import Enum


class Side(str, Enum):
    BID = "bid"
    ASK = "ask"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class StrategyType(str, Enum):
    SINGLE = "single"
    OCO = "oco"
    OTO = "oto"
    OTOCO = "otoco"


class LiquidityRole(str, Enum):
    MAKER = "maker"
    TAKER = "taker"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"


class InstrumentEventType(str, Enum):
    PRICE = "price"
    TRADES = "trades"
    ORDERBOOK = "orderbook"


class InstrumentStatus(str, Enum):
    DOWN = "down"
    UP = "up"


class TimeFrame(str, Enum):
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


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRADE = "trade"
    ESCROW = "escrow"


class CommandType(str, Enum):
    NEW_ORDER = "new_order"
    CANCEL_ORDER = "cancel_order"
    MODIFY_ORDER = "modify_order"
    NEW_INSTRUMENT = "new_instrument"


class MatchOutcome(Enum):
    FAILURE = 0  # 0 quantity matched
    PARTIAL = 1  # > 0 quantity matched
    SUCCESS = 2  # full quantity matched
    INSUFFICIENT_BALANCE = 3
