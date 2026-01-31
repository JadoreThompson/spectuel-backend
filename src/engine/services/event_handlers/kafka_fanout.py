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
    _CATEGORY_2_TOPIC = {
        EngineEventCategory.BALANCE: KAFKA_BALANCE_EVENTS_TOPIC,
        EngineEventCategory.ORDER: KAFKA_ORDER_EVENTS_TOPIC,
        EngineEventCategory.TRADE: KAFKA_INSTRUMENT_EVENTS_TOPIC,
    }

    def __init__(self, redis_client: Redis):
        self._kafka_producer = AsyncKafkaProducer()
        self._kafka_consumer = AsyncKafkaConsumer(KAFKA_ENGINE_EVENTS_TOPIC)
        self._redis_client = redis_client
        self._task: asyncio.Task | None = None

    async def run(self):
        try:
            await self._kafka_producer.start()
            await self._kafka_consumer.start()

            async for msg in self._kafka_consumer:
                event_category = None
                for k, v in msg.headers:
                    if k == "event_category":
                        event_category = v.decode()
                        break

                if event_category is None:
                    continue

                topic = self.__class__._CATEGORY_2_TOPIC.get(event_category)
                if topic is None:
                    continue

                await self._kafka_producer.send_and_wait(
                    topic,
                    msg.value,
                    headers=list(msg.headers),
                )

                if event_category == EngineEventCategory.TRADE:
                    event = json.loads(msg.value.decode())
                    await self._set_price(event["symbol"], event["price"])
        except Exception as e:
            print(f"Kafka fanout error: {e}")
        finally:
            await self._kafka_producer.stop()
            await self._kafka_consumer.stop()

    async def _set_price(self, symbol: str, price: float) -> None:
        """Set's the price of the symbol within redis"""
        await self._redis_client.set(symbol, price)
