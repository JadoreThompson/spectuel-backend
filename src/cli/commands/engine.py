import click
import logging
import time
from multiprocessing import Process

from sqlalchemy import select

from config import HEARTBEAT_ITMEOUT, HEARTBEAT_SERVER_HOST, HEARTBEAT_SERVER_PORT
from db_models import Instruments
from engine.engine_orchestrator import EngineOrchestrator
from engine.enums import InstrumentStatus
from infra.db import get_db_sess_sync
from runners import run_runner, RunnerConfig, run_runner_v2


@click.group()
def engine():
    """Manages the engine"""
    pass


def get_symbols(limit: int = 1):
    if limit < 1:
        raise ValueError("limit must be >= 1")

    with get_db_sess_sync() as db_sess:
        symbols = db_sess.scalars(
            select(Instruments.symbol)
            .where(Instruments.status == InstrumentStatus.DEAD)
            .limit(limit)
        ).all()
    return symbols


@engine.command(name="run")
def engine_run():
    logger = logging.getLogger("main")

    symbols = get_symbols(limit=1)
    if not symbols:
        logger.info("No symbols to launch engines for")
        return

    logger.info(f"Launching engines for symbols: {", ".join(symbols)}")

    configs = tuple(
        RunnerConfig(
            cls=EngineOrchestrator,
            kwargs={
                "symbol": symbol,
                "shadow_kwargs": {
                    "heartbeat_host": HEARTBEAT_SERVER_HOST,
                    "heartbeat_port": HEARTBEAT_SERVER_PORT,
                    "heartbeat_interval": HEARTBEAT_ITMEOUT * 0.5,
                },
            },
            name=f"EngineOrchestrator-{symbol}",
        )
        for symbol in symbols
    )

    ps = [
        Process(target=run_runner_v2, args=(conf,), name=conf.name)
        for conf in configs
    ]

    for p in ps:
        p.start()

    try:
        while True:
            for p in ps:
                if not p.is_alive():
                    raise RuntimeError(f"Process '{p.name}' has died unexpectedly!")
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down all processes.")
    finally:
        for p in ps:
            if p.is_alive():
                logger.info(f"Shutting down process '{p.name}'...")
                p.kill()
                p.join(timeout=10)

        logger.info("All processes shut down.")
