import os
import shutil
import tempfile

import pytest
from src.engine.enums import Side

from engine.engine_orchestrator import EngineOrchestrator
from src.engine.restoration.engine_restorer import EngineRestorer
from src.engine.restoration.engine_snapshotter import EngineSnapshotter
from src.engine.loggers import WALogger
from tests.utils import create_new_order_command


@pytest.fixture
def tmp_dir_fixture():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def engine_orchestrator(spot_engine, tmp_dir_fixture):
    fpath = os.path.join(tmp_dir_fixture, "snapshots", spot_engine._ctx.symbol)
    os.makedirs(fpath)
    orch = EngineOrchestrator(engines=[spot_engine])
    
    yield orch, tmp_dir_fixture

    shutil.rmtree(tmp_dir_fixture)
    del orch


def test_engine_restoration_with_snapshot(
    engine_orchestrator, user_id_a, user_id_b
):
    engine_orchestrator, tmpdir = engine_orchestrator
    orch_payloads = engine_orchestrator._payloads
    spot_engine = orch_payloads[[*orch_payloads.keys()][0]][0]
    balance_manager = spot_engine._balance_manager
    symbol = spot_engine._ctx.symbol
    prev_file = WALogger._log_file

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
        
        # Snapshot
        sf = os.path.join(tmpdir, "snapshots", symbol)
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
            details={'test_field': 'test_value'},
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

    WALogger.set_file(prev_file)


def test_engine_restoration_no_snapshot(
    # spot_engine, balance_manager, user_id_a, user_id_b, instrument_id
    engine_orchestrator, user_id_a, user_id_b
):

    # prev_file = WALogger._log_file
    engine_orchestrator, tmpdir = engine_orchestrator
    orch_payloads = engine_orchestrator._payloads
    spot_engine = orch_payloads[[*orch_payloads.keys()][0]][0]
    balance_manager = spot_engine._balance_manager
    # instrument_id = spot_engine.instrument_id
    symbol = spot_engine._ctx.symbol
    prev_file = WALogger._log_file

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

    WALogger.set_file(prev_file)
