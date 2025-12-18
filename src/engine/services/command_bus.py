import json
from typing import AsyncGenerator

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from config import KAFKA_COMMANDS_TOPIC
from engine.commands import CommandT
from infra.kafka import AsyncKafkaConsumer, AsyncKafkaProducer


class CommandBus:
    def __init__(self):
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._initialised = False

    async def initialise(self):
        if self._initialised:
            return
        
        if self._producer is None:
            self._producer = AsyncKafkaProducer()
            await self._producer.start()
        if self._consumer is None:
            self._consumer = AsyncKafkaConsumer(KAFKA_COMMANDS_TOPIC)
            await self._consumer.start()
        
        self._initialised = True

    async def cleanup(self):
        if not self._initialised:
            raise RuntimeError("Command Bus not initialised")
        
        await self._producer.stop()
        await self._consumer.stop()
        self._initialised = False

    async def put(self, command: CommandT) -> None:
        await self.initialise()
        await self._producer.send(
            KAFKA_COMMANDS_TOPIC, command.model_dump_json().encode()
        )

    async def yield_command(self) -> AsyncGenerator[dict, None]:
        await self.initialise()
        async for msg in self._consumer:
            try:
                data = json.loads(msg.value.decode())
                yield data
            except json.JSONDecodeError:
                pass
