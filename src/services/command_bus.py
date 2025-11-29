from aiokafka import AIOKafkaProducer

from spectuel_engine_utils.commands import CommandT

from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_COMMANDS_TOPIC


class CommandBus:
    def __init__(self):
        self._producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)

    async def put(self, command: CommandT) -> None:
        await self._producer.send(KAFKA_COMMANDS_TOPIC, command.model_dump_json())
