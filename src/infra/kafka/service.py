import asyncio
import logging
from typing import ClassVar

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from config import KAFKA_BOOTSTRAP_SERVERS


class AsyncKafkaService:
    """
    Manages async kafka clients used during the lifecycle of
    the FastAPI server.
    """

    _producers: ClassVar[list[AIOKafkaProducer]] = []
    _producers_lock = asyncio.Lock()
    _consumers: ClassVar[dict[tuple[str], AIOKafkaConsumer]] = {}
    _consumers_lock = asyncio.Lock()
    _alive = False
    _logger: ClassVar[logging.Logger]

    @classmethod
    async def cleanup(cls):
        if not cls._alive:
            cls._logger.debug("Stop called")
            cls._alive = False

            cls._logger.debug("Stopping producers")
            async with cls._producers_lock:
                for prod in cls._producers:
                    await prod.stop()
                cls._producers = []
            cls._logger.debug("Producers stopped successfully")

            cls._logger.debug("Stopping consumers")
            async with cls._consumers_lock:
                for cons in cls._consumers.values():
                    await cons.stop()
                cls._consumers = {}
            cls._logger.debug("Consumer stopped successfully")

    @classmethod
    async def get_producer(cls) -> AIOKafkaProducer:
        if not cls._alive:
            raise ValueError(f"{cls.__name__} is closed.")

        prod = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        cls._producers.append(prod)
        await prod.start()
        return prod

    @classmethod
    async def get_consumer(cls, *topics: tuple[str]) -> AIOKafkaConsumer:
        if not cls._alive:
            raise ValueError(f"{cls.__name__} is closed.")

        consumer = AIOKafkaConsumer(*topics, bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        cls._consumers[topics] = consumer
        await consumer.start()
        return consumer
