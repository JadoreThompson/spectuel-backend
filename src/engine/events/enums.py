from enum import Enum


class InstrumentEventType(str, Enum):
    NEW_INSTRUMENT = "new"  # Instrument appended to the engine
    PRICE = "price"
    HEARTBEAT = "heartbeat"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"


class OrderEventType(str, Enum):
    ORDER_PLACED = "placed"
    ORDER_PARTIALLY_FILLED = "partially_filled"
    ORDER_FILLED = "filled"
    ORDER_MODIFIED = "modified"
    ORDER_MODIFY_REJECTED = "modify_rejected"
    ORDER_CANCELLED = "order_cancelled"


class TradeEventType(str, Enum):
    NEW_TRADE = "new"


class BalanceEventType(str, Enum):
    CASH_BALANCE_INCREASED = "cash_balance_increased"
    CASH_BALANCE_DECREASED = "cash_balance_decreased"
    CASH_ESCROW_INCREASED = "cash_escrow_increased"
    CASH_ESCROW_DECREASED = "cash_escrow_decreased"

    ASSET_BALANCE_INCREASED = "asset_balance_increased"
    ASSET_BALANCE_DECREASED = "asset_balance_decreased"
    ASSET_ESCROW_INCREASED = "asset_escrow_increased"
    ASSET_ESCROW_DECREASED = "asset_escrow_decreased"
    ASSET_BALANCE_SNAPSHOT = "asset_balance_snapshot"

    ASK_SETTLED = "ask_settled"
    BID_SETTLED = "bid_settled"

class LogEventType(str, Enum):
    INSTRUMENT_EVENT = "instrument_event"
    ORDER_EVENT = "order_event"
    TRADE_EVENT = "trade_event"
    COMMAND = "command"
    BALANCE_EVENT = "balance_event"