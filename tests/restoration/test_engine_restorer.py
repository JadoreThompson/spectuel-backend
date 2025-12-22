import os
import tempfile

import pytest

from src.engine.engine_orchestrator_v2 import EngineOrchestratorV2
from src.engine.enums import Side
# Importing WALogger through execution context to prevent
# incorrect referencing
from src.engine.execution_context import WALogger
from src.engine.restoration.engine_restorer import EngineRestorer
from src.engine.restoration.engine_snapshotter import EngineSnapshotter
from tests.utils import create_new_order_command


@pytest.fixture
def engine_orchestrator(spot_engine, tmp_dir):
    fpath = os.path.join(tmp_dir, "snapshots", spot_engine._ctx.symbol)
    os.makedirs(fpath, exist_ok=False)

    orch = EngineOrchestratorV2(symbols=[spot_engine._ctx.symbol])
    orch.initialise()

    yield orch, tmp_dir

    del orch


def test_engine_restoration_with_snapshot(engine_orchestrator, user_id_a, user_id_b):
    engine_orchestrator, tmp_dir = engine_orchestrator
    orch_payloads = engine_orchestrator._payloads
    spot_engine = orch_payloads[[*orch_payloads.keys()][0]][0]
    balance_manager = spot_engine._balance_manager
    symbol = spot_engine._ctx.symbol

    with open(os.path.join(tmp_dir, "0.log"), "a", encoding="utf8") as walf:
        WALogger.set_file(walf)

        # Simulate some operations
        balance_manager.increase_asset_balance(user_id_a, symbol, 20)
        cmd = create_new_order_command(
            user_id=user_id_a,
            symbol=symbol,
            side=Side.ASK,
            quantity=10,
            price=100.0,
        )
        engine_orchestrator.put(cmd)

        balance_manager.increase_cash_balance(user_id_b, 1000)
        cmd = create_new_order_command(
            user_id=user_id_b,
            symbol=symbol,
            side=Side.BID,
            quantity=5,
            price=100.0,
        )

        # Snapshot
        sf = os.path.join(tmp_dir, "snapshots", symbol)
        snapshotter = EngineSnapshotter(spot_engine, sf)
        ctx = snapshotter.snapshot()
        snapshotter.persist_snapshot(ctx)

        engine_orchestrator.put(cmd)

        # Simulate more operations
        cmd = create_new_order_command(
            user_id=user_id_a,
            symbol=symbol,
            side=Side.ASK,
            quantity=5,
            price=99.0,
            details={"test_field": "test_value"},
        )
        engine_orchestrator.put(cmd)

        # Restore
        restorer = EngineRestorer(sf, walf.name)
        restored_engine = restorer.get_restored_engine()

        # Assertions
        ctx = restored_engine._ctx
        ob = ctx.orderbook

        assert restored_engine is not None
        assert symbol == ctx.symbol
        assert len(ctx.order_store._orders) == 2
        assert len(ob.bids) == 0
        assert len(ob.asks) == 2


def test_engine_restoration_no_snapshot(engine_orchestrator, user_id_a, user_id_b):
    engine_orchestrator, tmpdir = engine_orchestrator
    orch_payloads = engine_orchestrator._payloads
    spot_engine = orch_payloads[[*orch_payloads.keys()][0]][0]
    balance_manager = spot_engine._balance_manager
    symbol = spot_engine._ctx.symbol

    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, "0.log"), "a") as walf:
            WALogger.set_file(walf)

            # Simulate some operations
            balance_manager.increase_asset_balance(user_id_a, symbol, 20)
            cmd = create_new_order_command(
                user_id=user_id_a,
                symbol=symbol,
                side=Side.ASK,
                quantity=10,
                price=100.0,
            )
            engine_orchestrator.put(cmd)

            balance_manager.increase_cash_balance(user_id_b, 1000)
            cmd = create_new_order_command(
                user_id=user_id_b,
                symbol=symbol,
                side=Side.BID,
                quantity=5,
                price=100.0,
            )
            engine_orchestrator.put(cmd)

            # Restore
            sf = os.path.join(tmpdir, "snapshots", symbol)
            os.makedirs(sf)
            restorer = EngineRestorer(sf, walf.name)
            restored_engine = restorer.get_restored_engine()

            assert restored_engine is not None
            assert symbol == restored_engine._ctx.symbol
            assert len(restored_engine._ctx.order_store._orders) == 1
            assert len(restored_engine._ctx.orderbook.bids) == 0
            assert len(restored_engine._ctx.orderbook.asks) == 1
