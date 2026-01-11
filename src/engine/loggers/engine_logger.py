import json
import uuid
from enum import Enum
from io import TextIOWrapper
from typing import Any, Callable, Union

from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_ENGINE_EVENTS_TOPIC,
    KAFKA_INSTRUMENT_EVENTS_TOPIC,
    KAFKA_ORDER_EVENTS_TOPIC,
)
from engine.decorators import ignore_system_user
from engine.enums import EngineEventCategory
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
from engine.events.enums import OrderEventType, BalanceEventType, LogEventType,InstrumentEventType
from infra.kafka import KafkaProducer


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


Hook = Callable[[bytes], Any]


class EngineLogger:
    _instances = {}
    _producer = KafkaProducer()

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

    def __new__(cls, name: str, *args, **kw):
        key = (cls, name)
        if key in cls._instances:
            return cls._instances[key]

        inst = super().__new__(cls)
        cls._instances[key] = inst
        return inst

    def __init__(
        self,
        name: str,
        on_log_event: Hook | None = None,
        on_log_command_event: Hook | None = None,
    ) -> None:
        if getattr(self, "_initialised", False):
            return

        self._name = name
        self.on_log_event = on_log_event
        self.on_log_command_event = on_log_command_event
        self._initialised = True

    @property
    def name(self) -> str:
        return self._name

    def log_event(
        self, event: dict | EngineEventBase, kafka_kwargs: dict | None = None
    ) -> None:
        try:
            serialised_event = self._serialise_event(event)
            if kafka_kwargs is None:
                kafka_kwargs = {}
            if "headers" in kafka_kwargs:
                kafka_kwargs["headers"] = self._build_headers(kafka_kwargs["headers"])

            self.__class__._producer.send(
                KAFKA_ENGINE_EVENTS_TOPIC, serialised_event, **kafka_kwargs
            )

            if self.on_log_event is not None:
                self.on_log_event(serialised_event)

        except ValueError:
            pass

    @staticmethod
    def _serialise_event(event: dict | EngineEventBase) -> bytes:
        if isinstance(event, dict):
            return json.dumps(event).encode()
        return event.model_dump_json().encode()

    def _write_event(self, typ: LogEventType, event: dict | EngineEventBase) -> None:

        f = self._ensure_file()
        record = LogEvent(type=typ, data=event)
        dumped = record.model_dump_json() + "\n"
        f.write(dumped)
        f.flush()  # Ensure durability

    def log_command_event(self, **kwargs) -> None:
        if self.on_log_command_event is not None:
            self.on_log_command_event(kwargs)

    @ignore_system_user
    def log_order_event(
        self, user_id: str, /, kafka_kwargs: dict | None = None, **kwargs
    ) -> None:
        event_cls = self._order_event_map[kwargs["type"]]
        event_cls(**kwargs)  # Validate

        if kafka_kwargs is None:
            kafka_kwargs = {}

        headers = kafka_kwargs.setdefault("headers", {})
        headers["user_id"] = user_id
        headers["event_category"] = EngineEventCategory.ORDER

        self.log_event(kwargs, kafka_kwargs)

    @ignore_system_user
    def log_trade_event(
        self, user_id: str, /, kafka_kwargs: dict | None = None, **kwargs
    ) -> None:
        NewTradeEvent(**kwargs)  # Validate

        if kafka_kwargs is None:
            kafka_kwargs = {}

        headers = kafka_kwargs.setdefault("headers", {})
        headers["user_id"] = user_id
        headers["event_category"] = EngineEventCategory.TRADE

        self.log_event(kwargs, kafka_kwargs)

    @ignore_system_user
    def log_balance_event(
        self,
        user_id: str | None = None,
        event: BalanceEventUnion | None = None,
        /,
        kafka_kwargs: dict | None = None,
        **kwargs,
    ) -> None:
        if event is None:
            event_cls = self._balance_event_map[kwargs["type"]]
            event_cls(**kwargs)  # Validate

            if kafka_kwargs is None:
                kafka_kwargs = {}

            headers = kafka_kwargs.setdefault("headers", {})
            if user_id is not None:
                headers["user_id"] = user_id
            headers["event_category"] = EngineEventCategory.BALANCE

            self.log_event(kwargs, kafka_kwargs)
        else:

            if kafka_kwargs is None:
                kafka_kwargs = {}

            headers = kafka_kwargs.setdefault("headers", {})
            if user_id is not None:
                headers["user_id"] = user_id
            headers["event_category"] = EngineEventCategory.BALANCE

            self.log_event(event, kafka_kwargs)

    def log_instrument_event(self, kafka_kwargs: dict | None = None, **kwargs) -> None:
        return

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    def _build_headers(self, data: dict) -> list[tuple[str, bytes]]:
        headers = []
        serialisers = {
            str: lambda v: v.encode(),
            list: lambda v: json.dumps(v).encode(),
            dict: lambda v: json.dumps(v).encode(),
        }

        for k, v in data.items():
            if type(k) != str:
                raise ValueError(f"Type of key '{k}' must be a string.")

            v_type = type(v)
            serialiser = serialisers.get(v_type)

            if serialiser:
                headers.append((k, serialiser(v)))
            else:
                raise ValueError(f"No serialiser for value {v} of type {v_type}")

        return headers

    @staticmethod
    def _get_kafka_topic(event_type: Enum):
        if isinstance(event_type, OrderEventType):
            return KAFKA_ORDER_EVENTS_TOPIC
        if isinstance(event_type, BalanceEventType):
            return KAFKA_BALANCE_EVENTS_TOPIC
        if isinstance(event_type, InstrumentEventType):
            return KAFKA_INSTRUMENT_EVENTS_TOPIC
        raise ValueError(f"Topic for '{event_type}' not found")
