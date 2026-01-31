from enum import Enum


class InstrumentEventType(str, Enum):
    ENGINE_CREATED = "instrument_engine_created"
    ORDERBOOK_SNAPSHOT = "instrument_orderbook_snapshot"
    NEW_TRADE = "instrument_new_trade"
    BAR_UPDATE = "instrument_bar_update"


class OrderbookEventType(str, Enum):
    SNAPSHOT = "snapshot"


class OrderEventType(str, Enum):
    ORDER_PLACED = "order_placed"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_FILLED = "order_filled"
    ORDER_MODIFIED = "order_modified"
    ORDER_MODIFY_REJECTED = "order_modify_rejected"
    ORDER_CANCELLED = "order_cancelled"


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


class CommandEventType(str, Enum):
    COMMAND_PROCESSED = "command_processed"
    COMMAND_RECEIVED = "command_received"


class BarEventType(str, Enum):
    BAR_UPDATE = "bar_update"

