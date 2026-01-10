import json
import logging
from queue import Queue
from types import MethodType
from typing import Hashable

from sqlalchemy import insert, update

from db_models import EngineContextSnapshots, Instruments
from engine.enums import InstrumentStatus
from engine.events.enums import CommandEventType, OrderEventType
from engine.execution_context import ExecutionContext
from engine.heartbeat import HeartbeatClient
from engine.loggers import ShadowEngineLogger
from engine.matching_engines import SpotEngine
from infra.db import get_db_sess_sync


class EngineShadow:
    def __init__(
        self,
        engine: SpotEngine,
        queue: Queue,
        sentinel: Hashable,
        snapshot_interval: int = 1000,
        heartbeat_host: str | None = None,
        heartbeat_port: int | None = None,
        heartbeat_interval: float | None = None,
    ):
        if snapshot_interval < 1:
            raise ValueError("snapshot interval must be greater than or equal to 1.")

        self._engine = engine
        self._ctx: ExecutionContext[ShadowEngineLogger] = engine.ctx
        self._queue = queue
        self._sentinel = sentinel
        self.snapshot_interval = snapshot_interval
        self._op_count = 0
        self._order_id_2_strategy_type = {}
        self._batch = []
        self._idx = 0

        if (
            heartbeat_host is not None
            and heartbeat_port is not None
            and heartbeat_interval is not None
        ):
            self._hb_client = HeartbeatClient(
                host=heartbeat_host,
                port=heartbeat_port,
                on_close=lambda: self._set_instrument_status(InstrumentStatus.DEAD),
            )
        self._logger = logging.getLogger(f"EngineSlot-{engine._ctx.symbol}")

    def run(self):
        self._apply_patches()
        cmd = None
        command_count = 0

        try:
            self._set_instrument_status(InstrumentStatus.ALIVE)
            
            while True:
                event_bytes = self._queue.get()
                if event_bytes == self._sentinel:
                    self._logger.info("Received sentinel, exiting loop")
                    break

                event = json.loads(event_bytes)
                event_type = event["type"]
                if event_type == CommandEventType.COMMAND_RECEIVED:
                    cmd = event["command"]
                elif cmd is not None:
                    self._batch.append(event)
                elif event_type == CommandEventType.COMMAND_PROCESSED:
                    if event["command_id"] != cmd["id"]:
                        raise ValueError(
                            f"Received command processed event for unknown command id {event['command_id']}"
                        )

                    self._engine.handle_command(cmd)
                    self._batch.clear()

                    if command_count >= self.snapshot_interval:
                        self._snapshot(cmd)
                        command_count = 0

                    cmd = None
        finally:
            self._hb_client.close()

    def _apply_patches(self):
        # Balance manager patches
        bal_manager_methods = (
            # Cash balance
            "increase_cash_balance",
            "decrease_cash_balance",
            "increase_cash_escrow",
            "decrease_cash_escrow",
            # Asset balance
            "increase_asset_balance",
            "decrease_asset_balance",
            "increase_asset_escrow",
            "decrease_asset_escrow",
            # Settlement
            "settle_ask",
            "settle_bid",
        )
        bal_manager = self._engine.balance_manager
        noop = lambda *args, **kw: None

        for name in bal_manager_methods:
            if not hasattr(bal_manager, name):
                continue
            setattr(bal_manager, name, MethodType(noop, bal_manager))

        # Engine patches
        setattr(
            self._engine,
            "_check_sufficient_balance",
            lambda *args, **kw: self._check_sufficient_balance(),
        )

        # Shadow logger
        self._ctx.engine_logger.on_log_event_request = (
            lambda *args, **kw: self._advance()
        )

    def _advance(self):
        self._idx += 1

    def _check_sufficient_balance(self) -> bool:
        if self._idx + 1 >= len(self._batch):
            return True

        return self._batch[self._idx + 1]["type"] != OrderEventType.ORDER_CANCELLED

    def _snapshot(self, cmd: dict) -> None:
        ctx = self._engine._ctx
        ctx_snapshot = ctx.to_dict()
        cmd_details = cmd["details"]

        with get_db_sess_sync() as db_sess:
            db_sess.execute(
                insert(EngineContextSnapshots).values(
                    symbol=ctx.symbol,
                    snapshot=ctx_snapshot,
                    topic=cmd_details["kafka_topic"],
                    partition=cmd_details["kafka_partition"],
                    offset=cmd_details["kafka_offset"],
                )
            )
            db_sess.commit()

    def _set_instrument_status(self, status: InstrumentStatus) -> None:
        with get_db_sess_sync() as db_sess:
            db_sess.execute(
                update(Instruments)
                .values(status=status.value)
                .where(Instruments.symbol == self._ctx.symbol)
            )
            db_sess.commit()
