import json
import logging
import threading
import time
from multiprocessing.queues import Queue as MPQueueT
from typing import Any

from kafka import KafkaConsumer
from pydantic import ValidationError
from sqlalchemy import select

from config import (
    HEARTBEAT_STALE_THRESHOLD,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_COMMANDS_TOPIC,
)
from db_models import EngineContextSnapshots, Instruments
from engine.engine_orchestrator import EngineOrchestrator
from engine.engine_orchestrator_v2 import EngineOrchestratorV2
from runners import BaseRunner
from utils.db import get_db_sess


class ListenerRunner(BaseRunner):
    def __init__(self, instrument_queue: MPQueueT, watchdog_ts) -> None:
        self._instrument_queue = instrument_queue
        self._watchdog_ts = watchdog_ts
        self._th = threading.Thread(
            target=self._th_target, name=f"{self.__class__.__name__}Thread", daemon=True
        )
        self._logger = logging.getLogger(self.__class__.__name__)

    def _get_symbols(self):
        with get_db_sess() as db_sess:
            iids = db_sess.scalars(select(Instruments.symbol)).all()
            return [str(iid) for iid in iids]

    def run(self) -> None:
        self._th.start()
        iids = self._get_symbols()
        orch = EngineOrchestratorV2(
            heartbeat_queue=self._instrument_queue, symbols=iids
        )
        orch.initialise()

        self._watchdog_ts.value = int(time.time())

        consumer = KafkaConsumer(
            KAFKA_COMMANDS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id="ingetsion_runner_group_v1",
        )

        self._logger.info(f"{self.__class__.__name__} started.")

        for msg in consumer:
            try:
                cmd: dict[str, Any] = json.loads(msg.value.decode())

                details = cmd.get("details")
                if not details:
                    cmd["details"] = {"kafka_offset": msg.offset}
                else:
                    details["kafka_offset"] = msg.offset
                orch.put(cmd)
                consumer.commit()

            except (json.JSONDecodeError, ValidationError):
                pass
            except Exception as e:
                self._logger.error(
                    f"Error processing command offset={msg.offset}: {e}",
                    exc_info=True,
                )

    def _th_target(self):
        while True:
            self._watchdog_ts.value = int(time.time())
            time.sleep(HEARTBEAT_STALE_THRESHOLD * 0.5)
