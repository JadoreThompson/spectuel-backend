import time
import logging
from typing import NamedTuple
from uuid import uuid4

from sqlalchemy import select

from db_models import EngineContextSnapshots, Instruments
from engine.commands import NewSingleOrderCommand
from engine.config import SYSTEM_USER_ID
from engine.enums import StrategyType, OrderType, Side, CommandType
from engine.execution_context import ExecutionContext
from engine.matching_engines import SpotEngine
from infra.db import get_db_sess_sync


logger = logging.getLogger(__name__)


class EngineLoadContext(NamedTuple):
    engine: SpotEngine
    topic: str | None  # Kafka topic
    partition: int | None  # Kafka partition
    offset: int | None  # Kafka offset


class EngineLoader:
    @classmethod
    def load_engines(cls, symbols: list[str] | None = None) -> list[EngineLoadContext]:
        """Loads engines from DB or Snapshots and returns a map of EngineSlots."""
        ctxs: list[EngineLoadContext] = []

        query = select(
            Instruments.symbol,
            Instruments.starting_price,
            EngineContextSnapshots.snapshot,
            EngineContextSnapshots.topic,
            EngineContextSnapshots.partition,
            EngineContextSnapshots.offset,
        ).join(
            EngineContextSnapshots,
            EngineContextSnapshots.symbol == Instruments.symbol,
            isouter=True,
        )

        if symbols:
            query = query.where(Instruments.symbol.in_(symbols))

        with get_db_sess_sync() as db_sess:
            data = db_sess.execute(query).all()

        for rec in data:
            symbol = rec.symbol

            # Restore or Create
            if rec.snapshot is not None:
                ctx = ExecutionContext.from_dict(rec.snapshot)
                engine = SpotEngine(rec.symbol, ctx=ctx)
                load_ctx = EngineLoadContext(
                    engine=engine,
                    topic=rec.topic,
                    partition=rec.partition,
                    offset=rec.offset,
                )
            else:
                engine = SpotEngine(symbol)
                engine._ctx.orderbook._cur_price = rec.starting_price
                cls._seed_liquidity(engine, symbol, rec.starting_price)
                load_ctx = EngineLoadContext(
                    engine=engine,
                    topic=None,
                    partition=None,
                    offset=None,
                )

            ctxs.append(load_ctx)

        logger.info(f"Loaded {len(ctxs)} engines.")
        return ctxs

    @staticmethod
    def _seed_liquidity(engine: SpotEngine, symbol: str, starting_price: float) -> None:
        """Injects initial orders directly into the engine."""
        logger.info(f"Seeding liquidity for {symbol} at {starting_price}")
        base_qty = 10.0

        for i in range(10):
            price = round(starting_price * (1 + (i * 0.005)), 2)
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
                limit_price=price,
                details={"note": "liquidity_seed"},
            )
            # Direct handle to avoid WAL logging/orchestrator overhead during seed
            engine.handle_command(cmd.model_dump(mode="json"))
