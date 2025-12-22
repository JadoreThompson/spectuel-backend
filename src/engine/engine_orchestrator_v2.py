import logging
import time
from multiprocessing.queues import Queue as MPQueueT
from uuid import uuid4

from sqlalchemy import select

from db_models import EngineContextSnapshots, Instruments
from engine.commands import NewSingleOrderCommand
from engine.config import SYSTEM_USER_ID
from engine.enums import StrategyType, OrderType, Side, CommandType
from engine.events.enums import InstrumentEventType
from engine.matching_engines import SpotEngine
from engine.loggers.wal_logger import WALogger
from engine.restoration.engine_restorer_v2 import EngineRestorerV2
from engine.restoration.engine_snapshotter import EngineSnapshotter
from engine.restoration.engine_snapshotter_v2 import EngineSnapshotterV2
from infra.db import get_db_sess_sync


class EngineOrchestratorV2:
    def __init__(
        self,
        symbols: list[str] | None = None,
        max_commands_per_snapshot: int = 1000,
        heartbeat_queue: MPQueueT | None = None,
    ) -> None:
        self._payloads: dict[str, tuple[SpotEngine, int, EngineSnapshotterV2]] = {}
        self._symbols = symbols
        
        if self._symbols is not None:
            for symbol in self._symbols:
                engine = SpotEngine(symbol)
                snapshotter = EngineSnapshotterV2(engine, symbol)
                self._payloads[symbol] = (engine, 0, snapshotter)

        self._max_commands_per_snapshot = max_commands_per_snapshot
        self._heartbeat_queue = heartbeat_queue

        self._wal_logger = WALogger(self.__class__.__name__)
        self._logger = logging.getLogger(self.__class__.__name__)

    def initialise(self) -> None:
        query = select(
            Instruments.symbol,
            Instruments.starting_price,
            EngineContextSnapshots.snapshot,
        )
        if self._symbols is not None:
            # Only these symbols otherwise get all
            query = query.where(Instruments.symbol.in_(self._symbols))

        query = query.join(
            EngineContextSnapshots,
            EngineContextSnapshots.symbol == Instruments.symbol,
            isouter=True,
        )

        with get_db_sess_sync() as db_sess:
            data = db_sess.execute(query).all()
            for rec in data:
                symbol = str(rec.symbol)

                if rec.snapshot is None:
                    engine = SpotEngine(symbol)
                    engine._ctx.orderbook._cur_price = rec.starting_price
                else:
                    restorer = EngineRestorerV2(rec.snapshot)
                    engine = restorer.get_restored_engine()

                snapshotter = EngineSnapshotterV2(engine, symbol)
                self._payloads[symbol] = (engine, 0, snapshotter)

                if rec.snapshot is None:
                    self.seed_liquidity(symbol, rec.starting_price)

                self._push_to_queue("add", symbol)

    def seed_liquidity(self, symbol: str, starting_price: float) -> None:
        """
        Injects a set of Ask orders to populate the book around the starting price.
        These orders belong to the SYSTEM_USER and bypass balance checks.
        """
        self._logger.info(f"Seeding liquidity for {symbol} at {starting_price}")

        base_qty = 10.0

        for i in range(10):
            price_level = starting_price * (1 + (i * 0.005))

            # Construct Command
            cmd = NewSingleOrderCommand(
                id=str(uuid4()),
                version=1,
                timestamp=int(time.time()),
                type=CommandType.NEW_ORDER,
                strategy_type=StrategyType.SINGLE,
                symbol=symbol,
                order_id=str(uuid4()),
                user_id=SYSTEM_USER_ID,
                order_type=OrderType.LIMIT,
                side=Side.ASK,
                quantity=base_qty,
                limit_price=round(price_level, 2),
                details={"note": "liquidity_seed"},
            )

            self.put(cmd.model_dump(mode="json"))

        self._logger.info(f"Seeded 10 Ask levels for {symbol}")

    def put(self, cmd: dict) -> None:
        self._wal_logger.log_command(cmd)

        symbol = cmd["symbol"]

        if (
            cmd["type"] == InstrumentEventType.NEW_INSTRUMENT
            and symbol not in self._payloads
        ):
            engine, counter, snapshotter = self._payloads[symbol]
            snapshotter = EngineSnapshotterV2(engine, engine._ctx.symbol)
            self._payloads[symbol] = (engine, counter, snapshotter)
            engine.handle_command(cmd)
            return

        if symbol not in self._payloads:
            raise ValueError(f"Received command for unknown symbol '{symbol}'")

        engine, counter, snapshotter = self._payloads[symbol]

        counter += 1
        if counter == self._max_commands_per_snapshot:
            snapshotter.snapshot()
            counter = 0

        self._payloads[symbol] = (engine, counter, snapshotter)

        try:
            engine.handle_command(cmd)
        except Exception as e:
            import traceback

            traceback.print_exc()
            self._logger.error(f"Received '{type(e)}' for command {cmd} - {e}")
            self._payloads.pop(symbol)
            self._push_to_queue("remove", symbol)

    def _push_to_queue(self, action: str, symbol: str):
        if self._heartbeat_queue is not None:
            self._heartbeat_queue.put_nowait((action, symbol))
