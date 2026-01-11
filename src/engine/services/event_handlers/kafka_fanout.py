import asyncio
import json

from redis.asyncio import Redis

from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_ENGINE_EVENTS_TOPIC,
    KAFKA_INSTRUMENT_EVENTS_TOPIC,
    KAFKA_ORDER_EVENTS_TOPIC,
)
from engine.enums import EngineEventCategory
from engine.events import BalanceEventType, OrderEventType
from engine.events.enums import InstrumentEventType
from infra.kafka import AsyncKafkaProducer, AsyncKafkaConsumer


class KafkaFanout:
    def __init__(self, redis_client: Redis):
        self._kafka_producer = AsyncKafkaProducer()
        self._kafka_consumer = AsyncKafkaConsumer(KAFKA_ENGINE_EVENTS_TOPIC)
        self._redis_client = redis_client
        self._category_2_topic: dict[str, str] = {}
        self._task: asyncio.Task | None = None

    def _init(self):
        for enum_type, topic in (
            (BalanceEventType, KAFKA_BALANCE_EVENTS_TOPIC),
            (OrderEventType, KAFKA_ORDER_EVENTS_TOPIC),
            (InstrumentEventType, KAFKA_INSTRUMENT_EVENTS_TOPIC),
        ):
            vals = enum_type.__members__.values()
            self._category_2_topic.update({val: topic for val in vals})

    async def run(self):
        self._init()

        try:
            await self._kafka_producer.start()
            await self._kafka_consumer.start()

            async for msg in self._kafka_consumer:
                for k, v in msg.headers:
                    if k == "event_category":
                        event_category = v.decode()
                        topic = self._category_2_topic.get(event_category)

                        if topic is None:
                            continue

                        await self._kafka_producer.send_and_wait(
                            topic,
                            msg.value,
                            headers=msg.headers,
                        )

                        if event_category == EngineEventCategory.TRADE:
                            event = json.loads(msg.value.decode())
                            await self._set_price(event["symbol"], event["price"])
        finally:
            await self._kafka_producer.stop()
            await self._kafka_consumer.stop()

    async def _set_price(self, symbol: str, price: float) -> None:
        """Set's the price of the symbol within redis"""
        await self._redis_client.set(symbol, price)
