from io import TextIOWrapper
from typing import Union

from engine.config import WAL_FPATH
from engine.decorators import ignore_system_user
from engine.events.enums import OrderEventType, BalanceEventType, LogEventType
from engine.events import (
    EngineEventBase,
    AssetBalanceDecreasedEvent,
    AssetBalanceIncreasedEvent,
    AssetEscrowDecreasedEvent,
    AssetEscrowIncreasedEvent,
    CashBalanceDecreasedEvent,
    CashBalanceIncreasedEvent,
    CashEscrowIncreasedEvent,
    CashEscrowDecreasedEvent,
    BidSettledEvent,
    AskSettledEvent,
    OrderPlacedEvent,
    OrderCancelledEvent,
    OrderPartiallyFilledEvent,
    OrderModifiedEvent,
    OrderModifyRejectedEvent,
    OrderFilledEvent,
    NewTradeEvent,
    LogEvent,
)
from engine.loggers import EngineLogger
from engine.restoration.restoration_manager import RestorationManager


BalanceEventUnion = Union[
    CashBalanceIncreasedEvent,
    CashBalanceDecreasedEvent,
    CashEscrowIncreasedEvent,
    CashEscrowDecreasedEvent,
    AssetBalanceIncreasedEvent,
    AssetBalanceDecreasedEvent,
    AssetEscrowIncreasedEvent,
    AssetEscrowDecreasedEvent,
    BidSettledEvent,
    AskSettledEvent,
]


class WALogger(EngineLogger):
    _log_file: TextIOWrapper | None = None
    _order_event_map = {
        OrderEventType.ORDER_PLACED: OrderPlacedEvent,
        OrderEventType.ORDER_PARTIALLY_FILLED: OrderPartiallyFilledEvent,
        OrderEventType.ORDER_FILLED: OrderFilledEvent,
        OrderEventType.ORDER_MODIFIED: OrderModifiedEvent,
        OrderEventType.ORDER_MODIFY_REJECTED: OrderModifyRejectedEvent,
        OrderEventType.ORDER_CANCELLED: OrderCancelledEvent,
    }
    _balance_event_map = {
        BalanceEventType.CASH_BALANCE_INCREASED: CashBalanceIncreasedEvent,
        BalanceEventType.CASH_BALANCE_DECREASED: CashBalanceDecreasedEvent,
        BalanceEventType.CASH_ESCROW_INCREASED: CashEscrowIncreasedEvent,
        BalanceEventType.CASH_ESCROW_DECREASED: CashEscrowDecreasedEvent,
        BalanceEventType.ASSET_BALANCE_INCREASED: AssetBalanceIncreasedEvent,
        BalanceEventType.ASSET_BALANCE_DECREASED: AssetBalanceDecreasedEvent,
        BalanceEventType.ASSET_ESCROW_DECREASED: AssetEscrowDecreasedEvent,
        BalanceEventType.ASSET_ESCROW_INCREASED: AssetEscrowIncreasedEvent,
        BalanceEventType.BID_SETTLED: BidSettledEvent,
        BalanceEventType.ASK_SETTLED: AskSettledEvent,
    }

    @property
    def name(self) -> str:
        return self._name

    @classmethod
    def set_file(cls, file: TextIOWrapper) -> None:
        """
        Set the WAL file handle once. The file must be opened in append mode.
        """
        if not isinstance(file, TextIOWrapper):
            raise TypeError("set_file expects a TextIOWrapper")

        if "a" not in file.mode:
            raise ValueError("WAL file must be opened in append mode ('a' or 'a+')")

        cls._log_file = file

    @classmethod
    def _ensure_file(cls) -> TextIOWrapper:
        if cls._log_file is None:
            cls._log_file = open(WAL_FPATH, "a")
        return cls._log_file

    def _write_event(self, typ: LogEventType, event: dict | EngineEventBase) -> None:
        if RestorationManager.is_restoring(self._name):
            return

        f = self._ensure_file()
        record = LogEvent(type=typ, data=event)
        f.write(record.model_dump_json() + "\n")
        f.flush()  # Ensure durability

    def log_command(self, command: dict) -> None:
        self._write_event(LogEventType.COMMAND, command)

    @ignore_system_user
    def log_order_event(self, user_id: str, /, **kwargs) -> None:
        event_cls = self._order_event_map[kwargs["type"]]
        event = event_cls(**kwargs)  # Validate
        self._write_event(LogEventType.ORDER_EVENT, event)
        self.log_event(kwargs, {"user_id": user_id})

    @ignore_system_user
    def log_trade_event(self, user_id: str, **kwargs) -> None:
        NewTradeEvent(**kwargs)  # Validate
        self._write_event(LogEventType.TRADE_EVENT, kwargs)
        self.log_event(kwargs, {"user_id": user_id})

    def log_balance_event(
        self,
        event: BalanceEventUnion | None = None,
        user_id: str | None = None,
        /,
        **kwargs,
    ) -> None:
        if event is None:
            event_cls = self._balance_event_map[kwargs["type"]]
            event_cls(**kwargs)  # Validate
            self._write_event(LogEventType.BALANCE_EVENT, kwargs)
            self.log_event(kwargs, {"user_id": user_id})
        else:
            self._write_event(LogEventType.BALANCE_EVENT, event)
            self.log_event(event, {"user_id": user_id})

    def log_instrument_event(self, **kwargs) -> None:
        self._write_event(LogEventType.INSTRUMENT_EVENT, kwargs)
