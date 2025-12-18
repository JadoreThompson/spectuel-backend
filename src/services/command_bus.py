from typing import ClassVar

from aiokafka import AIOKafkaProducer

from config import KAFKA_COMMANDS_TOPIC
from engine.commands import CommandT
from infra.kafka import AsyncKafkaProducer


class CommandBus:
    _producer: ClassVar[AIOKafkaProducer | None] = None

    @classmethod
    async def put(cls, command: CommandT) -> None:
        if cls._producer is None:
            cls._producer = AsyncKafkaProducer()
            await cls._producer.start()
        await cls._producer.send(
            KAFKA_COMMANDS_TOPIC, command.model_dump_json().encode()
        )
