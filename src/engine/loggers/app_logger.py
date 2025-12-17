import json
from enum import Enum
from kafka import KafkaProducer

from engine.events import EngineEventBase
from engine.events.enums import OrderEventType, BalanceEventType, TradeEventType
from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_ORDER_EVENTS_TOPIC,
    KAFKA_TRADE_EVENTS_TOPIC,
)


class AppLogger:
    _instances = {}
    _producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)

    def __new__(cls, name: str):
        key = (cls, name)
        if key in cls._instances:
            return cls._instances[key]

        inst = super().__new__(cls)
        cls._instances[key] = inst
        return inst

    def __init__(self, name: str) -> None:
        if getattr(self, "_initialised", False):
            return

        self._name = name
        self._initialised = True

    @property
    def name(self):
        return self._name

    def log_event(self, event: dict | EngineEventBase, headers: dict) -> None:
        try:
            if isinstance(event, dict):
                typ = event['type']
                dumped = json.dumps(event).encode()
            else:
                typ = event.type
                dumped = event.model_dump_json().encode()

            topic = self._get_kafka_topic(typ)
            self.__class__._producer.send(topic, dumped, headers=self._build_headers(headers))
        except ValueError:
            pass

    def _build_headers(self, data: dict):
        headers = []
        serialisers = {
            str: lambda v: v.encode(),
            list: lambda v: json.dumps(v).encode(),
            dict: lambda v: json.dumps(v).encode()
        }

        for k, v in data.items():
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
        if isinstance(event_type, TradeEventType):
            return KAFKA_TRADE_EVENTS_TOPIC
        raise ValueError("Topic for '{event_type}' not found")
