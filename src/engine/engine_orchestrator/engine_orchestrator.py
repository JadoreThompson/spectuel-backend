import json
import logging
import multiprocessing as mp

from aiokafka import TopicPartition, ConsumerRecord
from sqlalchemy import update

from config import KAFKA_ENGINE_EVENTS_TOPIC
from db_models import Instruments
from engine.engine_orchestrator.engine_shadow_manager import EngineShadowManager
from engine.enums import InstrumentStatus
from engine.loggers import EngineLogger, ShadowEngineLogger
from engine.matching_engines import SpotEngine
from engine.restoration.engine_loader import EngineLoader
from engine.execution_context import ExecutionContext
from infra.db import get_db_sess_sync
from infra.kafka import KafkaConsumer



class EngineOrchestrator:
    def __init__(self, symbol: str, shadow: bool = True) -> None:
        self._symbol = symbol
        self._shadow = shadow
        self._engine: SpotEngine | None = None

        self._shadow_ps: mp.Process | None = None
        self._kafka_consumer: KafkaConsumer | None = None

        name = self.__class__.__name__
        self._engine_logger = EngineLogger(name)
        self._logger = logging.getLogger(name)

    def run(self):
        self._logger.info("Loading snapshot and context...")
        load_ctx = EngineLoader.load_engines([self._symbol])[0]
        self._logger.info(
            "Context loaded - ",
            f"symbol={load_ctx.engine._ctx.symbol}, ",
            f"topic={load_ctx.topic}, ",
            f"partition={load_ctx.partition}, ",
            f"offset={load_ctx.offset}, ",
        )
        self._engine = load_ctx.engine

        topic = load_ctx.topic or KAFKA_ENGINE_EVENTS_TOPIC
        self._kafka_consumer = KafkaConsumer(
            topics=[topic], group_id=f"engine-orchestrator-{self._symbol}"
        )

        if load_ctx.partition is not None and load_ctx.offset is not None:
            tp = TopicPartition(topic=topic, partition=load_ctx.partition)
            self._kafka_consumer.assign([tp])
            self._kafka_consumer.seek(tp, load_ctx.offset + 1)

        if self._shadow:
            self._logger.info(f"Creating shadow slot")
            self._create_shadow()

        try:
            self._logger.info(f"Updating status to {InstrumentStatus.ALIVE}")
            self._set_instrument_status(InstrumentStatus.ALIVE)

            for msg in self._kafka_consumer:
                cmd = self._parse_message(msg)
                if cmd is None:
                    continue

                if self._shadow_ps is not None and not self._shadow_ps.is_alive():
                    self._logger.error(
                        f"Shadow process for {self._symbol} has died unexpectedly."
                    )
                    raise RuntimeError("Shadow process has died.")

                self._engine.handle_command(cmd)

        except Exception:
            self._logger.error(
                f"Error handling command for {self._symbol} - {cmd}", exc_info=True
            )
            self._logger.info(f"Updating status to {InstrumentStatus.DEAD}")
            self._set_instrument_status(InstrumentStatus.DEAD)
            raise

    def _create_shadow(self) -> None:
        """
        Creates the shadow engine
        """
        shadow_ctx = ExecutionContext.from_dict(self._engine._ctx.to_dict())
        shadow_ctx.engine_logger = ShadowEngineLogger(f"ShadowEngine-{self._symbol}")
        shadow_engine = SpotEngine(self._symbol, ctx=shadow_ctx)
        shadow_ctx.engine = shadow_engine
        self._logger.info(f"Created shadow engine for {self._symbol}")

        event_queue = mp.Queue()
        log_event_hook = lambda event: event_queue.put_nowait(event)
        self._engine.ctx.engine_logger.on_log_command_event = log_event_hook
        self._engine.ctx.engine_logger.on_log_event = log_event_hook
        self._logger.info("Added push to queue hook for log command event and log event")

        manager = EngineShadowManager(shadow_engine, event_queue, sentinel=-1, snapshot_interval=10_000)
        self._logger.info("Created snapshot manager for shadow engine.")

        self._logger.info("Launching shadow process...")
        self._shadow_ps = mp.Process(
            target=manager.run,
            daemon=True,
            name=f"{type(manager).__name__}-{self._symbol}",
        )
        self._shadow_ps.start()
        self._logger.info("Shadow process launched successfully.")

    def _parse_message(self, msg: ConsumerRecord) -> dict | None:
        headers = msg.headers
        is_command = False
        for k, v in headers:
            if k == "event_category":
                is_command = v.decode() == "command"
                break

        if not is_command:
            return

        cmd = json.loads(msg.value.decode())
        if cmd["symbol"] != self._symbol:
            return

        if not cmd.get("details"):
            cmd["details"] = {}

        cmd["details"]["kafka_topic"] = msg.topic
        cmd["details"]["kafka_partition"] = msg.partition
        cmd["details"]["kafka_offset"] = msg.offset

        return cmd

    def _set_instrument_status(self, status: InstrumentStatus) -> None:
        with get_db_sess_sync() as db_sess:
            db_sess.execute(
                update(Instruments)
                .values(status=status.value)
                .where(Instruments.symbol == self._symbol)
            )
            db_sess.commit()
