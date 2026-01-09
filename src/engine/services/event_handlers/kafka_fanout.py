import asyncio

from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_ORDER_EVENTS_TOPIC,
    KAFKA_TRADE_EVENTS_TOPIC,
)
from engine.events import BalanceEventType, OrderEventType, TradeEventType
from infra.kafka import AsyncKafkaProducer, AsyncKafkaConsumer


class KafkaFanout:
    def __init__(
        self, kafka_producer: AsyncKafkaProducer, kafka_consumer: AsyncKafkaConsumer
    ):
        self._kafka_producer = kafka_producer
        self._kafka_consumer = kafka_consumer
        self._routers: dict[str, str] = {}
        self._task: asyncio.Task | None = None

    def _init(self):
        for enum_type, topic in (
            (BalanceEventType, KAFKA_BALANCE_EVENTS_TOPIC),
            (OrderEventType, KAFKA_ORDER_EVENTS_TOPIC),
            (TradeEventType, KAFKA_TRADE_EVENTS_TOPIC),
        ):
            vals = enum_type.__members__.values()
            self._routers.update({val: topic for val in vals})

    async def run(self):
        self._init()

        try:
            await self._kafka_producer.start()
            await self._kafka_consumer.start()

            async for msg in self._kafka_consumer:
                for k, v in msg.headers:
                    if k == "event_category":
                        event_category = v.decode()
                        topic = self._routers.get(event_category)
                        if topic:
                            await self._kafka_producer.send_and_wait(
                                topic,
                                msg.value,
                                headers=msg.headers,
                            )
        finally:
            await self._kafka_producer.stop()
            await self._kafka_consumer.stop()
