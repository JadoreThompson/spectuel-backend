from config import KAFKA_ENGINE_EVENTS_TOPIC
from engine.commands import CommandBase
from engine.enums import EngineEventCategory
from infra.kafka import AsyncKafkaProducer

KAFKA_PRODUCER = AsyncKafkaProducer()


async def put_command(command: CommandBase):
    await KAFKA_PRODUCER.send(
        KAFKA_ENGINE_EVENTS_TOPIC,
        command.model_dump_json(),
        headers=[("event_category", EngineEventCategory.COMMAND.encode())],
    )
