import logging
from typing import ClassVar

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from config import KAFKA_BOOTSTRAP_SERVERS


class KafkaService:
    _producer: ClassVar[AIOKafkaProducer]
    _consumers: ClassVar[dict[tuple[str], AIOKafkaConsumer]] = {}
    _alive = False
    _logger: ClassVar[logging.Logger]

    @classmethod
    async def start(cls):
        if cls._alive:
            cls._producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
            await cls._producer.start()
            cls._logger = logging.getLogger(cls.__name__)
            cls._alive = True

    @classmethod
    async def stop(cls):
        cls._logger.debug("Stop called")
        cls._closed = True

        cls._logger.debug("Stopping producer")
        await cls._producer.stop()
        cls._logger.debug("Producer stopped successfully")

        cls._logger.debug("Stopping consumers")
        for cons in cls._consumers.values():
            await cons.stop()
        cls._logger.debug("Consumer stopped successfully")

    @classmethod
    def get_producer(cls) -> AIOKafkaProducer:
        if not cls._alive:
            raise ValueError(f"{cls.__name__} is closed.")
        return cls._producer

    @classmethod
    async def get_consumer(cls, *topics: tuple[str]) -> AIOKafkaConsumer:
        if not cls._alive:
            raise ValueError(f"{cls.__name__} is closed.")

        if topics not in cls._consumers:
            consumer = AIOKafkaConsumer(
                *topics, bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS
            )
            cls._consumers[topics] = consumer
            await consumer.start()
            return consumer
        else:
            return cls._consumers[topics]
