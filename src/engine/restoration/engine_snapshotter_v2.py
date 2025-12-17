import json
import os

from sqlalchemy import insert

from db_models import EngineContextSnapshots
from engine.matching_engines import SpotEngine
from utils.db import get_db_sess


class EngineSnapshotterV2:
    def __init__(self, engine: SpotEngine, symbol: str):
        self._engine = engine
        self._symbol = symbol

    def snapshot(self) -> dict:
        return self._engine._ctx.serialise()

    def persist_snapshot(self, snapshot: dict) -> None:
        with get_db_sess() as db_sess:
            db_sess.execute(
                insert(EngineContextSnapshots).values(
                    symbol=self._symbol, snapshot=snapshot
                )
            )
            db_sess.commit()
