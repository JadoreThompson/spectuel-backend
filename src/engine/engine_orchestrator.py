import logging
import os
from multiprocessing.queues import Queue as MPQueueT


from engine.config import ENGINE_SNAPSHOT_FOLDER
from engine.events.enums import InstrumentEventType
from engine.loggers import WALogger
from engine.matching_engines import SpotEngine
from engine.restoration.engine_restorer import EngineRestorer
from engine.restoration.engine_snapshotter import EngineSnapshotter


class EngineOrchestrator:
    def __init__(
        self,
        engines: list[SpotEngine] | None = None,
        snapshot_folders: list[str] | None = None,
        max_commands_per_snapshot: int = 1000,
        queue: MPQueueT | None = None,
    ) -> None:
        self._payloads: dict[str, tuple[SpotEngine, int, EngineSnapshotter]] = {}
        self._snapshot_folders = snapshot_folders
        self._max_commands_per_snapshot = max_commands_per_snapshot
        self._queue = queue
        self._wal_logger = WALogger("EngineOrchestrator")
        self._logger = logging.getLogger(self.__class__.__name__)

        if engines is not None:
            for engine in engines:
                snapshotter = EngineSnapshotter(
                    engine, os.path.join(ENGINE_SNAPSHOT_FOLDER, engine.instrument_id)
                )
                self._payloads[engine.instrument_id] = (engine, 0, snapshotter)
                self._push_to_queue("add", engine.instrument_id)

    def initialise(self) -> None:
        if self._snapshot_folders is None:
            return

        for snapshot_folder in self._snapshot_folders:
            restorer = EngineRestorer(snapshot_folder)
            engine = restorer.get_restored_engine()
            snapshotter = EngineSnapshotter(
                engine, os.path.join(ENGINE_SNAPSHOT_FOLDER, engine.instrument_id)
            )
            self._payloads[engine.instrument_id] = (engine, 0, snapshotter)
            self._push_to_queue("add", engine.instrument_id)

    def put(self, cmd: dict) -> None:
        self._wal_logger.log_command(cmd)

        instrument_id = cmd["instrument_id"]

        if (
            cmd["type"] == InstrumentEventType.NEW_INSTRUMENT
            and instrument_id not in self._payloads
        ):
            engine, counter, snapshotter = self._payloads[instrument_id]
            snapshotter = EngineSnapshotter(engine)
            self._payloads[instrument_id] = (engine, counter, snapshotter)
            engine.handle_command(cmd)
            return

        if instrument_id not in self._payloads:
            raise ValueError(
                f"Received command for unknown instrument_id '{instrument_id}'"
            )

        engine, counter, snapshotter = self._payloads[instrument_id]

        counter += 1
        if counter == self._max_commands_per_snapshot:
            snapshotter.snapshot()
            counter = 0

        self._payloads[instrument_id] = (engine, counter, snapshotter)

        try:
            engine.handle_command(cmd)
        except Exception as e:
            self._logger.error(
                f"Received '{e.__class__.__name__}' for command {cmd} - {str(e)}"
            )
            self._payloads.pop(instrument_id)
            self._push_to_queue("remove", instrument_id)

    def _push_to_queue(self, action: str, instrument_id: str):
        if self._queue is not None:
            self._queue.put_nowait((action, instrument_id))
