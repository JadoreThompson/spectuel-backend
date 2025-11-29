from typing import ClassVar
from aiokafka import AIOKafkaProducer

from spectuel_engine_utils.commands import CommandT

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_COMMANDS_TOPIC


class CommandBus:
    _producer: ClassVar[AIOKafkaProducer | None] = None

    @classmethod
    async def put(cls, command: CommandT) -> None:
        if cls._producer is None:
            cls._producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
            await cls._producer.start()
        await cls._producer.send(KAFKA_COMMANDS_TOPIC, command.model_dump_json().encode())
