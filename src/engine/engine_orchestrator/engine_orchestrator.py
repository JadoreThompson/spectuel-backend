import json
import logging
import multiprocessing as mp
from typing import Any

from aiokafka import TopicPartition, ConsumerRecord

from config import KAFKA_ENGINE_EVENTS_TOPIC
from engine.enums import EngineEventCategory, InstrumentStatus
from engine.loggers import EngineLogger
from engine.matching_engines import SpotEngine
from engine.restoration.engine_loader import EngineLoader
from infra.kafka import KafkaConsumer


class EngineOrchestrator:
    def __init__(
        self,
        symbol: str,
        shadow: bool = True,
        shadow_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            symbol (str): Which symbol's commands to process
            shadow (bool, optional): Whether or not to create a shadow engine.
                If false the snapshot engine will not be created and the snapshots
                therefore will not be created either.
            shadow_kwargs (dict[str, Any], optional): Kwargs to be passed onto the EngineShadow.
                The engine, event queue and sentinel will be passed on by the EngineOrchestrator but
                all other paremeter values can be defined here.
        """
        self._symbol = symbol
        self._shadow = shadow
        self._shadow_kwargs = shadow_kwargs
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
            f"Context loaded - symbol={load_ctx.engine._ctx.symbol}, "
            f"topic={load_ctx.topic}, partition={load_ctx.partition}, "
            f"offset={load_ctx.offset}"
        )
        self._engine = load_ctx.engine

        topic = load_ctx.topic or KAFKA_ENGINE_EVENTS_TOPIC
        self._kafka_consumer = KafkaConsumer(
            topic, group_id=f"engine-orchestrator-{self._symbol}"
        )

        if load_ctx.partition is not None and load_ctx.offset is not None:
            tp = TopicPartition(topic=topic, partition=load_ctx.partition)
            self._kafka_consumer.assign([tp])
            # +1 to skip the last fully processed command
            self._kafka_consumer.seek(tp, load_ctx.offset + 1)

        if self._shadow:
            self._logger.info(f"Creating shadow engine for {self._symbol}")
            self._create_shadow()

        try:
            self._logger.info(f"Updating status to {InstrumentStatus.ALIVE}")

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

        except:
            self._logger.error(
                f"Error handling command for {self._symbol} - {cmd}", exc_info=True
            )
            raise

    def _create_shadow(self) -> None:
        """
        Creates the shadow engine and launches it within a seperate
        process.
        """
        # Get the engine context as a dict (picklable)
        engine_ctx_dict = self._engine._ctx.to_dict()

        event_queue = mp.Queue()
        log_event_hook = lambda event: event_queue.put_nowait(event)
        self._engine.ctx.engine_logger.on_log_command_event = log_event_hook
        self._engine.ctx.engine_logger.on_log_event = log_event_hook
        self._logger.info(
            "Added push to queue hook for log command event and log event"
        )

        # Import the helper function here to avoid circular imports
        from engine.engine_orchestrator.engine_shadow import _run_shadow_in_subprocess

        self._logger.info("Launching shadow process...")
        self._shadow_ps = mp.Process(
            target=_run_shadow_in_subprocess,
            args=(
                engine_ctx_dict,
                self._symbol,
                event_queue,
                -1,  # sentinel
                10_000,  # snapshot_interval
                self._shadow_kwargs.get("heartbeat_host") if self._shadow_kwargs else None,
                self._shadow_kwargs.get("heartbeat_port") if self._shadow_kwargs else None,
                self._shadow_kwargs.get("heartbeat_interval") if self._shadow_kwargs else None,
            ),
            daemon=True,
            name=f"EngineShadow-{self._symbol}",
        )
        self._shadow_ps.start()
        self._logger.info("Shadow process launched successfully.")

    def _parse_message(self, msg: ConsumerRecord) -> dict | None:
        headers = msg.headers
        is_command = False
        symbol = None

        for k, v in headers:
            if k == "event_category":
                is_command = v.decode() == EngineEventCategory.COMMAND
            elif k == "symbol":
                symbol = v.decode()

        if not is_command or symbol != self._symbol:
            return

        cmd = json.loads(msg.value.decode())
        if not cmd.get("details"):
            cmd["details"] = {}

        cmd["details"]["kafka_topic"] = msg.topic
        cmd["details"]["kafka_partition"] = msg.partition
        cmd["details"]["kafka_offset"] = msg.offset

        return cmd
