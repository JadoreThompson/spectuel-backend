import kafka
import aiokafka

from config import KAFKA_BOOTSTRAP_SERVERS


class KafkaProducer(kafka.KafkaProducer):
    def __init__(self, **configs):
        super().__init__(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            **configs,
        )


class KafkaConsumer(kafka.KafkaConsumer):
    def __init__(self, *topics, **configs):
        super().__init__(
            *topics,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            **configs,
        )


class AsyncKafkaProducer(aiokafka.AIOKafkaProducer):
    def __init__(self, *args, **kw):
        super().__init__(*args, bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS, **kw)


class AsyncKafkaConsumer(aiokafka.AIOKafkaConsumer):
    def __init__(self, *args, **kw):
        super().__init__(*args, bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS, **kw)
