import json
import os
from typing import Type


from engine.config import WAL_FPATH
from engine.events import LogEvent
from engine.events.enums import OrderEventType, LogEventType
from engine.execution_context import ExecutionContext
from engine.matching_engines import SpotEngine
from engine.orderbook import OrderBook
from engine.restoration.method_patch_manager import MethodPatchManager
from engine.restoration.restoration_manager import RestorationManager
from engine.services.balance_manager import BalanceManager
from engine.stores import OrderStore


class EngineRestorer:
    def __init__(self, snapshot_folder: str, wal_fpath: str = WAL_FPATH) -> None:
        self._snapshot_folder = snapshot_folder
        self._wal_fpath = wal_fpath

        self._idx = 0
        self._engine: SpotEngine | None = None
        self._wal_records: list[LogEvent] = []

        self._ctx: ExecutionContext | None = None
        self._reached_command = False
        self._restored = False

        self._engine_pm = None
        self._bm_pm = None

    def _load_log_records(self) -> None:
        with open(self._wal_fpath, "r") as f:
            self._wal_records = [LogEvent.model_validate_json(line) for line in f]

    def _load_snapshot_ctxs(self) -> None:
        files: list[str] = os.listdir(self._snapshot_folder)
        instrument_id: str = os.path.basename(self._snapshot_folder)
        if not files:
            self._engine = SpotEngine(instrument_id=instrument_id)
            self._ctx = ExecutionContext(
                engine=self._engine,
                orderbook=OrderBook(),
                order_store=OrderStore(),
                instrument_id=instrument_id,
            )
            self._engine._ctx = self._ctx
            return

        latest_snapshot_fname = max(
            os.listdir(self._snapshot_folder),
            key=lambda x: int(x.split(".json")[0]),
        )

        with open(
            os.path.join(self._snapshot_folder, latest_snapshot_fname), "rb"
        ) as f:
            ctx_data = json.load(f)

        self._engine = SpotEngine(instrument_id=instrument_id)
        self._ctx = ExecutionContext.from_dict(ctx_data, engine=self._engine)
        self._engine._ctx = self._ctx

    def get_restored_engine(self) -> SpotEngine:
        self._load_log_records()
        self._load_snapshot_ctxs()

        self._bm_pm: MethodPatchManager[Type[BalanceManager]] = MethodPatchManager(
            BalanceManager, self._build_balance_nop_patches()
        )
        self._engine_pm: MethodPatchManager[SpotEngine] = MethodPatchManager(
            self._engine,
            {
                "_check_sufficient_balance": (
                    self._engine._check_sufficient_balance,
                    self._check_sufficient_balance,
                )
            },
        )

        try:
            self._apply_patches()

            while self._idx < len(self._wal_records):
                cur_record = self._wal_records[self._idx]

                if cur_record.type == LogEventType.COMMAND:
                    command = cur_record.data

                    inst = command["instrument_id"]
                    if inst == self._ctx.instrument_id:

                        if self._ctx.command_id == command["id"]:
                            self._reached_command = True
                            self._idx += 1
                            continue

                        if self._reached_command or self._ctx.command_id is None:
                            self._engine.handle_command(command)

                self._idx += 1

            return self._engine
        finally:
            if not self._restored:
                self._restore_patches()

    def _apply_patches(self) -> None:
        RestorationManager.set_predicate(
            self._engine.instrument_id, lambda: self._check_is_restoring()
        )
        self._bm_pm.patch()
        self._engine_pm.patch()

    def _restore_patches(self) -> None:
        self._bm_pm.restore()
        self._engine_pm.restore()
        RestorationManager.remove(self._engine.instrument_id)
        self._engine = None
        self._bm_pm = None
        self._engine_pm = None
        self._restored = True

    def _check_is_restoring(self) -> bool:
        self._idx += 1
        if self._idx >= len(self._wal_records):
            self._restore_patches()
            return False
        return True

    def _check_sufficient_balance(self, *args, **kwargs):
        """
        Mimics the old behaviour:
        If the next event is ORDER_CANCELLED then we know it was insufficient funds.
        Otherwise allow.
        """
        if self._idx + 1 >= len(self._wal_records):
            return self._engine._check_sufficient_balance(*args, **kwargs)

        next_type = self._wal_records[self._idx + 1].data.get("type")
        allowed = next_type != OrderEventType.ORDER_CANCELLED
        self._idx += 1
        return allowed

    @staticmethod
    def _build_balance_nop_patches():
        """Generate a dict mapping each BalanceManager method -> no-op."""
        nop = lambda *a, **k: None
        names = [
            "get_available_cash_balance",
            "get_cash_escrow",
            "increase_cash_balance",
            "decrease_cash_balance",
            "increase_cash_escrow",
            "decrease_cash_escrow",
            "get_available_asset_balance",
            "increase_asset_balance",
            "decrease_asset_balance",
            "increase_asset_escrow",
            "decrease_asset_escrow",
            "settle_ask",
            "settle_bid",
        ]
        return {name: (getattr(BalanceManager, name), nop) for name in names}
