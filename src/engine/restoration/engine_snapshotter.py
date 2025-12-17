import json
import os

from engine.matching_engines import SpotEngine


class EngineSnapshotter:
    def __init__(self, engine: SpotEngine, snapshot_folder: str):
        self._engine = engine
        self._snapshot_folder = snapshot_folder
        self._counter = -1

    def snapshot(self) -> dict:
        return self._engine._ctx.serialise()

    def persist_snapshot(self, snapshot: dict) -> None:
        if self._counter == -1:
            files = os.listdir(self._snapshot_folder)
            self._counter = len(files)

        fpath = os.path.join(self._snapshot_folder, f"{self._counter}.json")
        with open(fpath, "w") as f:
            json.dump(snapshot, f, indent=4)

        self._counter += 1
