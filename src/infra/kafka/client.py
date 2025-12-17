import kafka
import aiokafka

from config import KAFKA_BOOTSTRAP_SERVERS


AIO_KAFKA_PRODUCER: aiokafka.AIOKafkaProducer = None


def KafkaProducer():
    return kafka.KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)


def KafkaConsumer(*args, **kw):
    return kafka.KafkaConsumer(*args, **kw, bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)


async def AsyncKafkaProducer(*args, **kw):
    prod = aiokafka.AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    await prod.start()


async def AsyncKafkaConsumer(*args, **kw):
    prod = aiokafka.AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    await prod.start()
