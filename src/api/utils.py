from config import KAFKA_ENGINE_EVENTS_TOPIC
from engine.commands import CommandBase
from engine.enums import EngineEventCategory
from infra.kafka import AsyncKafkaProducer


KAFKA_PRODUCER: AsyncKafkaProducer | None = None


async def get_kafka_producer() -> AsyncKafkaProducer:
    global KAFKA_PRODUCER

    if KAFKA_PRODUCER is None:
        KAFKA_PRODUCER = AsyncKafkaProducer()
        await KAFKA_PRODUCER.start()
    return KAFKA_PRODUCER


async def put_command(command: CommandBase, symbol: str):
    await (await get_kafka_producer()).send(
        KAFKA_ENGINE_EVENTS_TOPIC,
        command.model_dump_json().encode(),
        headers=[
            ("event_category", EngineEventCategory.COMMAND.encode()),
            ("symbol", symbol.encode()),
        ],
        key=symbol.encode(),
    )
